#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    start_backend_if_needed();
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if !cfg!(target_os = "macos") {
                    shutdown_owned_services();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Kattappa AI OS desktop");
}

fn start_backend_if_needed() {
    if backend_ready() {
        return;
    }
    let Some(root) = find_project_root() else {
        return;
    };
    let script = root.join("backend").join("run_server.py");
    let Some(python) = find_python(&root) else {
        return;
    };
    let runtime = runtime_dir(&root);
    let _ = std::fs::create_dir_all(&runtime);
    let child = std::process::Command::new(python)
        .arg(script)
        .current_dir(&root)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn();
    if let Ok(child) = child {
        let _ = std::fs::write(runtime.join("backend.pid"), child.id().to_string());
        wait_for_backend();
    }
}

fn runtime_dir(root: &std::path::Path) -> std::path::PathBuf {
    if cfg!(target_os = "macos") {
        if let Some(home) = std::env::var_os("HOME") {
            return std::path::PathBuf::from(home)
                .join("Library")
                .join("Application Support")
                .join("Kattappa AI OS")
                .join("runtime");
        }
    }
    root.join("runtime")
}

fn backend_ready() -> bool {
    let Ok(mut stream) = std::net::TcpStream::connect_timeout(
        &std::net::SocketAddr::from(([127, 0, 0, 1], 8000)),
        std::time::Duration::from_millis(700),
    ) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(std::time::Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(std::time::Duration::from_secs(2)));
    if std::io::Write::write_all(
        &mut stream,
        b"GET /ready HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
    )
    .is_err()
    {
        return false;
    }
    let mut buffer = [0_u8; 256];
    match std::io::Read::read(&mut stream, &mut buffer) {
        Ok(size) => String::from_utf8_lossy(&buffer[..size]).contains("200"),
        Err(_) => false,
    }
}

fn wait_for_backend() {
    for _ in 0..30 {
        if backend_ready() {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(500));
    }
}

fn find_project_root() -> Option<std::path::PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors() {
            if ancestor.join("backend").join("run_server.py").exists() {
                return Some(ancestor.to_path_buf());
            }
        }
    }
    let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    for ancestor in manifest_dir.ancestors() {
        if ancestor.join("backend").join("run_server.py").exists() {
            return Some(ancestor.to_path_buf());
        }
    }
    None
}

fn find_python(root: &std::path::Path) -> Option<std::path::PathBuf> {
    let candidates = if cfg!(target_os = "windows") {
        vec![
            root.join("ai_system_env")
                .join("Scripts")
                .join("pythonw.exe"),
            root.join("ai_system_env")
                .join("Scripts")
                .join("python.exe"),
        ]
    } else {
        vec![root.join("ai_system_env").join("bin").join("python")]
    };
    for candidate in candidates {
        if candidate.exists() {
            return Some(candidate);
        }
    }
    if cfg!(target_os = "windows") {
        Some(std::path::PathBuf::from("python"))
    } else {
        Some(std::path::PathBuf::from("python3"))
    }
}

fn shutdown_owned_services() {
    if let Some(script) = find_shutdown_script() {
        if cfg!(target_os = "windows") {
            let _ = std::process::Command::new("powershell")
                .args([
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script.to_string_lossy().as_ref(),
                ])
                .spawn();
        } else {
            let _ = std::process::Command::new("sh").arg(script).spawn();
        }
    }
}

fn find_shutdown_script() -> Option<std::path::PathBuf> {
    let script_name = if cfg!(target_os = "windows") {
        "Shutdown_Kattappa_AI_OS.ps1"
    } else {
        "shutdown_kattappa.sh"
    };
    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors() {
            let candidate = ancestor.join(script_name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }

    let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    for ancestor in manifest_dir.ancestors() {
        let candidate = ancestor.join(script_name);
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}
