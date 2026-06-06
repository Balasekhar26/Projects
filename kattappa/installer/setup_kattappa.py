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
            "KATTAPPA_SHARED_IMPROVEMENT_REPO_PATH", "docs/SHARED_IMPROVEMENTS.md"
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


def create_desktop_shortcut() -> None:
    if platform.system().lower() != "windows":
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
        commands = ["$shell = New-Object -ComObject WScript.Shell;"]
        for shortcut in shortcut_paths:
            commands.extend(
                [
                    f"$shortcut = $shell.CreateShortcut('{shortcut}');",
                    f"$shortcut.TargetPath = '{launcher}';",
                    f"$shortcut.WorkingDirectory = '{ROOT}';",
                    "$shortcut.Arguments = '';",
                    "$shortcut.Description = 'Kattappa AI OS Assistant';",
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
        if shutil.which("npm") and (DESKTOP_DIR / "package.json").exists():
            print("Starting desktop web UI...")
            subprocess.Popen(["npm", "run", "dev"], cwd=DESKTOP_DIR)
            time.sleep(3)
            webbrowser.open("http://127.0.0.1:5173")
        else:
            webbrowser.open("http://127.0.0.1:8000/docs")
        print("Kattappa AI OS is running. Press Ctrl+C here to stop the backend.")
        backend.wait()
    except KeyboardInterrupt:
        backend.terminate()
    return 0


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
            "  macOS: grant Screen Recording for vision and Accessibility for desktop control."
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
