#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                shutdown_owned_services();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Sekhar AI OS desktop");
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
        "Shutdown_Sekhar_AI_OS.ps1"
    } else {
        "shutdown_universal_ai.sh"
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
