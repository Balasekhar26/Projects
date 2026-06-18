from __future__ import annotations

import argparse
import ctypes
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / "ai_system_env"
BACKEND_ENV = ROOT / "backend" / ".env"
DESKTOP_DIR = ROOT / "apps" / "desktop"
DESKTOP_ICON = DESKTOP_DIR / "src-tauri" / "icons" / "icon.ico"
INSTALLATION_AGREEMENT = ROOT / "docs" / "INSTALLATION_AGREEMENT.md"
CORE_PYTHON_PACKAGES = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "python-dotenv",
    "pyyaml",
    "langgraph",
    "langchain",
    "langchain-ollama",
    "ollama",
    "chromadb",
    "playwright",
    "mss",
    "pillow",
    "pytesseract",
    "httpx",
    "psutil",
    "pytest",
    "pandas>=2.2.3,<3",
    "torch>=2.0.0",
    "einops==0.8.1",
    "huggingface_hub==0.33.1",
    "safetensors==0.6.2",
]


@dataclass(frozen=True)
class MachineProfile:
    tier: str
    cpu_logical: int
    ram_gb: float
    fast: str
    general: str
    coder: str
    power: str
    vision: str
    reasoning: str
    whisper: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install and run Kattappa AI OS Assistant."
    )
    parser.add_argument(
        "--launch", action="store_true", help="Launch Kattappa AI OS after setup."
    )
    parser.add_argument(
        "--no-npm", action="store_true", help="Skip desktop npm dependency install."
    )
    parser.add_argument(
        "--profile-only",
        action="store_true",
        help="Only detect specs and write backend/.env.",
    )
    parser.add_argument(
        "--no-python-deps", action="store_true", help="Create env but skip pip install."
    )
    parser.add_argument(
        "--accept-agreement",
        action="store_true",
        help="Accept docs/INSTALLATION_AGREEMENT.md without an interactive prompt.",
    )
    parser.add_argument(
        "--print-agreement",
        action="store_true",
        help="Print the installation agreement and exit.",
    )
    args = parser.parse_args()

    print("Kattappa AI OS setup")
    print(f"Root: {ROOT}")
    if args.print_agreement:
        print_installation_agreement()
        return 0
    if not args.profile_only:
        require_installation_agreement(args.accept_agreement)
    profile = detect_machine_profile()
    print(
        f"Detected profile: {profile.tier} ({profile.cpu_logical} logical CPU, {profile.ram_gb} GB RAM)"
    )
    write_backend_env(profile)

    if args.profile_only:
        print(f"Wrote adaptive config: {BACKEND_ENV}")
        return 0

    python_exe = ensure_venv()
    if not args.no_python_deps:
        install_python_deps(python_exe)
        install_playwright_browser(python_exe)
    if not args.no_npm:
        install_desktop_deps()
    prepare_macos_privacy_preflight(python_exe)
    create_desktop_shortcut()

    print("\nSetup complete.")
    print("Configured models:")
    print(f"  fast={profile.fast}")
    print(f"  general={profile.general}")
    print(f"  coder={profile.coder}")
    print(f"  power={profile.power}")
    print(f"  vision={profile.vision}")
    print(
        "\nOllama is optional for setup, but local chat needs Ollama running with at least one configured model."
    )
    print_os_setup_hints()

    if args.launch:
        return launch(python_exe)
    return 0


def detect_machine_profile() -> MachineProfile:
    cpu = os.cpu_count() or 2
    ram = detect_ram_gb()
    if ram >= 96 and cpu >= 16:
        return MachineProfile(
            tier="maximum",
            cpu_logical=cpu,
            ram_gb=ram,
            fast="qwen3:4b",
            general="qwen3:14b",
            coder="qwen2.5-coder:14b",
            power="qwen3:30b",
            vision="qwen3-vl:8b",
            reasoning="gpt-oss:20b",
            whisper="medium",
        )
    if ram >= 48 and cpu >= 8:
        return MachineProfile(
            tier="full_potential",
            cpu_logical=cpu,
            ram_gb=ram,
            fast="qwen3:4b",
            general="qwen3:8b",
            coder="qwen2.5-coder:7b",
            power="qwen3:30b",
            vision="qwen3-vl:8b",
            reasoning="gpt-oss:20b",
            whisper="small",
        )
    if ram >= 24 and cpu >= 6:
        return MachineProfile(
            tier="recommended",
            cpu_logical=cpu,
            ram_gb=ram,
            fast="qwen2.5:0.5b",
            general="qwen3:4b",
            coder="qwen2.5-coder:3b",
            power="qwen3:8b",
            vision="qwen3-vl:8b",
            reasoning="gpt-oss:20b",
            whisper="small",
        )
    return MachineProfile(
        tier="minimum",
        cpu_logical=cpu,
        ram_gb=ram,
        fast="qwen2.5:0.5b",
        general="phi3:latest",
        coder="qwen2.5-coder:3b",
        power="qwen3:4b",
        vision="disabled",
        reasoning="disabled",
        whisper="base",
    )


def detect_ram_gb() -> float:
    system = platform.system().lower()
    try:
        if system == "windows":

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.ullTotalPhys / (1024**3), 1)
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024**3), 1)
    except Exception:
        return 0.0


def write_backend_env(profile: MachineProfile) -> None:
    BACKEND_ENV.parent.mkdir(parents=True, exist_ok=True)
    existing = read_env(BACKEND_ENV)
    values = {
        **existing,
        "OLLAMA_HOST": existing.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "KATTAPPA_SHELL_ENABLED": existing.get("KATTAPPA_SHELL_ENABLED", "false"),
        "KATTAPPA_DESKTOP_ENABLED": existing.get("KATTAPPA_DESKTOP_ENABLED", "false"),
        "KATTAPPA_SCREEN_CAPTURE_ENABLED": existing.get(
            "KATTAPPA_SCREEN_CAPTURE_ENABLED", "false"
        ),
        "KATTAPPA_DATA_DIR": existing.get(
            "KATTAPPA_DATA_DIR", str(default_data_dir())
        ),
        "KATTAPPA_CLUSTER_ENABLED": existing.get("KATTAPPA_CLUSTER_ENABLED", "false"),
        "KATTAPPA_CLUSTER_PAIRING_REQUIRED": existing.get(
            "KATTAPPA_CLUSTER_PAIRING_REQUIRED", "true"
        ),
        "KATTAPPA_CLUSTER_AUTO_CONNECT_AFTER_PAIRING": existing.get(
            "KATTAPPA_CLUSTER_AUTO_CONNECT_AFTER_PAIRING", "true"
        ),
        "KATTAPPA_CLUSTER_TRUSTED_NETWORK_ONLY": existing.get(
            "KATTAPPA_CLUSTER_TRUSTED_NETWORK_ONLY", "true"
        ),
        "KATTAPPA_REMOTE_ACTIONS_NEED_APPROVAL": existing.get(
            "KATTAPPA_REMOTE_ACTIONS_NEED_APPROVAL", "true"
        ),
        "KATTAPPA_UNPAIRED_IMPROVEMENT_CHECK_ENABLED": existing.get(
            "KATTAPPA_UNPAIRED_IMPROVEMENT_CHECK_ENABLED", "true"
        ),
        "KATTAPPA_UNPAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS": existing.get(
            "KATTAPPA_UNPAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS", "24"
        ),
        "KATTAPPA_UNPAIRED_IMPROVEMENT_CHECK_REQUIRES_APPROVAL": existing.get(
            "KATTAPPA_UNPAIRED_IMPROVEMENT_CHECK_REQUIRES_APPROVAL", "true"
        ),
        "KATTAPPA_PAIRED_IMPROVEMENT_CHECK_ENABLED": existing.get(
            "KATTAPPA_PAIRED_IMPROVEMENT_CHECK_ENABLED", "true"
        ),
        "KATTAPPA_PAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS": existing.get(
            "KATTAPPA_PAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS", "24"
        ),
        "KATTAPPA_SHARED_IMPROVEMENT_REPO_PATH": existing.get(
            "KATTAPPA_SHARED_IMPROVEMENT_REPO_PATH", "docs/IMPROVEMENT_REGISTRY.md"
        ),
        "KATTAPPA_SHARED_IMPROVEMENT_AUTO_APPLY": existing.get(
            "KATTAPPA_SHARED_IMPROVEMENT_AUTO_APPLY", "false"
        ),
        "KATTAPPA_MACHINE_TIER": profile.tier,
        "KATTAPPA_MODEL_FAST": profile.fast,
        "KATTAPPA_MODEL_GENERAL": profile.general,
        "KATTAPPA_MODEL_CODER": profile.coder,
        "KATTAPPA_MODEL_POWER": profile.power,
        "KATTAPPA_MODEL_VISION": profile.vision,
        "KATTAPPA_MODEL_REASONING": profile.reasoning,
        "KATTAPPA_WHISPER_MODEL": profile.whisper,
    }
    lines = [
        "# Generated by installer/setup_kattappa.py",
        "# Edit safely; rerun setup to regenerate adaptive defaults.",
    ]
    lines.extend(f"{key}={value}" for key, value in values.items())
    BACKEND_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_data_dir() -> Path:
    system = platform.system().lower()
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "Kattappa AI OS"
    return ROOT


def update_backend_env(updates: dict[str, str]) -> None:
    values = read_env(BACKEND_ENV)
    values.update(updates)
    lines = [
        "# Generated by installer/setup_kattappa.py",
        "# Edit safely; rerun setup to regenerate adaptive defaults.",
    ]
    lines.extend(f"{key}={value}" for key, value in values.items())
    BACKEND_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_installation_agreement() -> None:
    if INSTALLATION_AGREEMENT.exists():
        print(INSTALLATION_AGREEMENT.read_text(encoding="utf-8"))
        return
    print(
        "Kattappa AI OS installation agreement is missing. Installation cannot continue safely."
    )


def require_installation_agreement(accepted: bool) -> None:
    print_installation_agreement()
    if accepted:
        print("Installation agreement accepted by --accept-agreement.")
        return
    if not sys.stdin.isatty():
        raise SystemExit(
            "Installation agreement was not accepted. Rerun with --accept-agreement "
            "only after reading docs/INSTALLATION_AGREEMENT.md."
        )
    try:
        response = input("Type I AGREE to continue installation: ").strip()
    except EOFError as exc:
        raise SystemExit(
            "Installation agreement was not accepted. Run setup.bat "
            "from a visible Command Prompt, or pass --accept-agreement only after reading "
            "docs/INSTALLATION_AGREEMENT.md."
        ) from exc
    if response != "I AGREE":
        raise SystemExit("Installation cancelled because the agreement was not accepted.")


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ensure_venv() -> Path:
    python_exe = venv_python()
    if python_exe.exists():
        print(f"Python environment ready: {python_exe}")
        return python_exe
    print("Creating Python environment...")
    venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    return python_exe


def venv_python() -> Path:
    if platform.system().lower() == "windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def install_python_deps(python_exe: Path) -> None:
    requirements = ROOT / "backend" / "requirements.txt"
    print("Installing Python dependencies...")
    run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"])
    try:
        run([str(python_exe), "-m", "pip", "install", "-r", str(requirements)])
    except subprocess.CalledProcessError:
        print(
            "Full dependency install failed. Retrying core cross-platform dependencies."
        )
        print(
            "Optional desktop/voice/OCR adapters can be installed later from the Tools panel."
        )
        run([str(python_exe), "-m", "pip", "install", *CORE_PYTHON_PACKAGES])


def install_desktop_deps() -> None:
    npm = "npm.cmd" if platform.system().lower() == "windows" else "npm"
    if shutil.which(npm) is None:
        print(
            "npm not found; skipping desktop package install. Install Node.js for the desktop UI."
        )
        return
    print("Installing desktop UI dependencies...")
    run([npm, "install"], cwd=DESKTOP_DIR)


def install_playwright_browser(python_exe: Path) -> None:
    print("Preparing Playwright browser runtime...")
    try:
        run([str(python_exe), "-m", "playwright", "install", "chromium"])
    except subprocess.CalledProcessError:
        print(
            "Playwright Chromium install failed. Kattappa AI OS will still run; browser automation can be repaired later."
        )


def prepare_macos_privacy_preflight(python_exe: Path) -> None:
    if platform.system().lower() != "darwin":
        return
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    update_backend_env({"KATTAPPA_DATA_DIR": str(data_dir)})
    print("\nPreparing macOS privacy permissions during setup...")
    print(f"  Runtime data: {data_dir}")
    print("  Screen Recording is checked once now, not every time Kattappa opens.")
    env = os.environ.copy()
    env["KATTAPPA_DATA_DIR"] = str(data_dir)
    env["KATTAPPA_SCREEN_CAPTURE_ENABLED"] = "true"
    code = (
        "from backend.tools.screen_tools import read_screen_snapshot\n"
        "result = read_screen_snapshot()\n"
        "ok = bool(result.get('screenshot_path')) and not result.get('error')\n"
        "print(result.get('error') or result.get('text') or 'screen capture checked')\n"
        "raise SystemExit(0 if ok else 2)\n"
    )
    try:
        result = subprocess.run(
            [str(python_exe), "-c", code],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
    except Exception as exc:
        update_backend_env({"KATTAPPA_SCREEN_CAPTURE_ENABLED": "false"})
        print(f"  Screen Recording preflight skipped: {exc}")
        return
    if result.returncode == 0:
        update_backend_env({"KATTAPPA_SCREEN_CAPTURE_ENABLED": "true"})
        print("  Screen Recording ready for task-time screen commands.")
        return
    update_backend_env({"KATTAPPA_SCREEN_CAPTURE_ENABLED": "false"})
    detail = (result.stdout or result.stderr or "permission not granted").strip()
    print("  Screen Recording not enabled; Kattappa will stay quiet and use guidance fallback.")
    if detail:
        print(f"  {detail.splitlines()[-1]}")


def create_desktop_shortcut() -> None:
    system = platform.system().lower()
    if system == "darwin":
        create_macos_desktop_shortcut()
        return
    if system == "linux":
        create_linux_desktop_shortcut()
        return
    if system != "windows":
        return
    launcher = ROOT / "run.exe"
    if not launcher.exists():
        print("Skipping shortcut: run.exe is missing.")
        return
    try:
        desktop_candidates = {Path(os.environ.get("USERPROFILE", str(ROOT))) / "Desktop"}
        if os.environ.get("OneDrive"):
            desktop_candidates.add(Path(os.environ["OneDrive"]) / "Desktop")
        try:
            shell_desktop = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[Environment]::GetFolderPath('Desktop')",
                ],
                cwd=ROOT,
                text=True,
            ).strip()
            if shell_desktop:
                desktop_candidates.add(Path(shell_desktop))
        except Exception:
            pass
        shortcut_paths: list[Path] = []
        for desktop in sorted(desktop_candidates):
            desktop.mkdir(parents=True, exist_ok=True)
            shortcut_paths.append(desktop / "Kattappa AI OS.lnk")
            legacy = desktop / "Kattappa AI OS.lnk"
            if legacy.exists():
                shortcut_paths.append(legacy)
        icon_location = f"{DESKTOP_ICON if DESKTOP_ICON.exists() else launcher},0"
        commands = ["$shell = New-Object -ComObject WScript.Shell;"]
        for shortcut in shortcut_paths:
            commands.extend(
                [
                    f"$shortcut = $shell.CreateShortcut({_ps_quote(shortcut)});",
                    f"$shortcut.TargetPath = {_ps_quote(launcher)};",
                    f"$shortcut.WorkingDirectory = {_ps_quote(ROOT)};",
                    "$shortcut.Arguments = '';",
                    "$shortcut.Description = 'Kattappa AI OS Assistant';",
                    f"$shortcut.IconLocation = {_ps_quote(icon_location)};",
                    "$shortcut.Save();",
                ]
            )
        ps = (
            " ".join(commands)
        )
        subprocess.check_call(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            cwd=ROOT,
        )
        print("Desktop shortcuts ready:")
        for shortcut in shortcut_paths:
            print(f"  {shortcut}")
    except Exception as exc:
        print(f"Shortcut repair skipped: {exc}")


def create_linux_desktop_shortcut() -> None:
    try:
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            return
        shortcut = desktop / "kattappa-ai-os.desktop"
        if shortcut.exists():
            return
        launcher = ROOT / "setup.sh"
        content = f"""[Desktop Entry]
Type=Application
Name=Kattappa AI OS
Comment=Kattappa AI OS Assistant
Exec={launcher}
Icon={ROOT / "apps" / "desktop" / "src-tauri" / "icons" / "icon.png"}
Terminal=true
Categories=Utility;Development;
"""
        shortcut.write_text(content, encoding="utf-8")
        shortcut.chmod(0o755)
        print(f"Linux desktop shortcut ready: {shortcut}")
    except Exception as exc:
        print(f"Linux desktop shortcut skipped: {exc}")


def create_macos_desktop_shortcut() -> None:
    app = macos_app_bundle()
    if not app.exists():
        print(
            "Skipping macOS desktop shortcut: native app is not built yet. "
            "Run `npm run tauri:build` in apps/desktop, then rerun setup."
        )
        return
    desktop = Path.home() / "Desktop"
    shortcut = desktop / "Kattappa AI OS.app"
    try:
        desktop.mkdir(parents=True, exist_ok=True)
        if shortcut.is_symlink() and shortcut.resolve() == app.resolve():
            print(f"macOS desktop shortcut ready: {shortcut}")
            return
        if shortcut.exists() or shortcut.is_symlink():
            print(f"Skipping macOS desktop shortcut: {shortcut} already exists.")
            return
        shortcut.symlink_to(app, target_is_directory=True)
        print(f"macOS desktop shortcut ready: {shortcut}")
    except Exception as exc:
        print(f"macOS desktop shortcut skipped: {exc}")


def macos_app_bundle() -> Path:
    return (
        DESKTOP_DIR
        / "src-tauri"
        / "target"
        / "release"
        / "bundle"
        / "macos"
        / "Kattappa AI OS.app"
    )


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def launch(python_exe: Path) -> int:
    if platform.system().lower() == "windows":
        launcher = ROOT / "run.exe"
        if launcher.exists():
            return subprocess.call([str(launcher)], cwd=ROOT)
    print("Starting backend...")
    backend = subprocess.Popen(
        [
            str(python_exe),
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
    )
    try:
        wait_for_ready()
        if open_native_desktop_app():
            print("Native desktop app opened.")
        elif shutil.which("npm") and (DESKTOP_DIR / "package.json").exists():
            start_desktop_web_ui()
        else:
            webbrowser.open("http://127.0.0.1:8000/docs")
        print("Kattappa AI OS is running. Press Ctrl+C here to stop the backend.")
        backend.wait()
    except KeyboardInterrupt:
        backend.terminate()
    return 0


def open_native_desktop_app() -> bool:
    system = platform.system().lower()
    if system == "darwin":
        bundle = macos_app_bundle()
        if bundle.exists() and shutil.which("open"):
            subprocess.Popen(["open", str(bundle)], cwd=ROOT)
            return True
    if system == "linux":
        executable = (
            DESKTOP_DIR
            / "src-tauri"
            / "target"
            / "release"
            / "kattappa-ai-os-desktop"
        )
        if executable.exists():
            subprocess.Popen([str(executable)], cwd=ROOT)
            return True
    return False


def open_in_app_window(url: str) -> bool:
    system = platform.system().lower()
    candidates = []
    if system == "windows":
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for cmd in ("msedge", "chrome"):
            path = shutil.which(cmd)
            if path:
                candidates.append(path)
    elif system == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        for cmd in ("google-chrome", "chromium", "microsoft-edge"):
            path = shutil.which(cmd)
            if path:
                candidates.append(path)
    elif system == "linux":
        for cmd in ("google-chrome", "chromium-browser", "chromium", "microsoft-edge"):
            path = shutil.which(cmd)
            if path:
                candidates.append(path)

    for exe in candidates:
        if Path(exe).exists() or shutil.which(exe):
            try:
                subprocess.Popen([str(exe), f"--app={url}"])
                return True
            except Exception:
                pass
    return False


def start_desktop_web_ui() -> None:
    print("Native desktop app is not built yet. Starting desktop dev UI...")
    subprocess.Popen(["npm", "run", "dev"], cwd=DESKTOP_DIR)
    time.sleep(3)
    url = "http://127.0.0.1:5173"
    if open_in_app_window(url):
        print("Opened desktop app window in App Mode.")
    else:
        webbrowser.open(url)


def wait_for_ready() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/ready", timeout=2
            ) as response:
                if response.status < 500:
                    print("Backend ready.")
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Backend did not become ready within 60 seconds.")


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+ " + " ".join(command))
    subprocess.check_call(command, cwd=cwd)


def print_os_setup_hints() -> None:
    system = platform.system().lower()
    print("\nOS feature notes:")
    if system == "windows":
        print(
            "  Windows: desktop control and speech use built-in adapters when enabled."
        )
        print(
            "  Optional: install Tesseract OCR and Ollama for full local AI features."
        )
    elif system == "darwin":
        print(
            "  macOS: setup runs Screen Recording preflight once; Accessibility is only needed for approved desktop control."
        )
        print(
            "  Optional: install Tesseract with Homebrew and Ollama for local models."
        )
    elif system == "linux":
        print("  Linux: install Tauri WebKit packages for native desktop builds.")
        print("  Optional: install tesseract-ocr and speech-dispatcher or espeak.")
        print(
            "  Desktop control depends on the active X11/Wayland session permissions."
        )
    else:
        print(
            "  This OS can run the backend if Python dependencies install successfully."
        )
        print("  Native desktop, vision, voice, and control may need manual adapters.")


if __name__ == "__main__":
    raise SystemExit(main())
