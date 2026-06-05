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
    "pandas==2.2.2",
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
        description="Install and run Universal AI / Sekhar AI OS."
    )
    parser.add_argument(
        "--launch", action="store_true", help="Launch Universal AI after setup."
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

    print("Universal AI setup")
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
        "SEKHAR_SHELL_ENABLED": existing.get("SEKHAR_SHELL_ENABLED", "false"),
        "SEKHAR_DESKTOP_ENABLED": existing.get("SEKHAR_DESKTOP_ENABLED", "false"),
        "SEKHAR_CLUSTER_ENABLED": existing.get("SEKHAR_CLUSTER_ENABLED", "false"),
        "SEKHAR_CLUSTER_PAIRING_REQUIRED": existing.get(
            "SEKHAR_CLUSTER_PAIRING_REQUIRED", "true"
        ),
        "SEKHAR_CLUSTER_AUTO_CONNECT_AFTER_PAIRING": existing.get(
            "SEKHAR_CLUSTER_AUTO_CONNECT_AFTER_PAIRING", "true"
        ),
        "SEKHAR_CLUSTER_TRUSTED_NETWORK_ONLY": existing.get(
            "SEKHAR_CLUSTER_TRUSTED_NETWORK_ONLY", "true"
        ),
        "SEKHAR_REMOTE_ACTIONS_NEED_APPROVAL": existing.get(
            "SEKHAR_REMOTE_ACTIONS_NEED_APPROVAL", "true"
        ),
        "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_ENABLED": existing.get(
            "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_ENABLED", "true"
        ),
        "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS": existing.get(
            "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS", "24"
        ),
        "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_REQUIRES_APPROVAL": existing.get(
            "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_REQUIRES_APPROVAL", "true"
        ),
        "SEKHAR_PAIRED_IMPROVEMENT_CHECK_ENABLED": existing.get(
            "SEKHAR_PAIRED_IMPROVEMENT_CHECK_ENABLED", "true"
        ),
        "SEKHAR_PAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS": existing.get(
            "SEKHAR_PAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS", "24"
        ),
        "SEKHAR_SHARED_IMPROVEMENT_REPO_PATH": existing.get(
            "SEKHAR_SHARED_IMPROVEMENT_REPO_PATH", "docs/SHARED_IMPROVEMENTS.md"
        ),
        "SEKHAR_SHARED_IMPROVEMENT_AUTO_APPLY": existing.get(
            "SEKHAR_SHARED_IMPROVEMENT_AUTO_APPLY", "false"
        ),
        "SEKHAR_MACHINE_TIER": profile.tier,
        "SEKHAR_MODEL_FAST": profile.fast,
        "SEKHAR_MODEL_GENERAL": profile.general,
        "SEKHAR_MODEL_CODER": profile.coder,
        "SEKHAR_MODEL_POWER": profile.power,
        "SEKHAR_MODEL_VISION": profile.vision,
        "SEKHAR_MODEL_REASONING": profile.reasoning,
        "SEKHAR_WHISPER_MODEL": profile.whisper,
    }
    lines = [
        "# Generated by installer/setup_universal_ai.py",
        "# Edit safely; rerun setup to regenerate adaptive defaults.",
    ]
    lines.extend(f"{key}={value}" for key, value in values.items())
    BACKEND_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_installation_agreement() -> None:
    if INSTALLATION_AGREEMENT.exists():
        print(INSTALLATION_AGREEMENT.read_text(encoding="utf-8"))
        return
    print(
        "Universal AI installation agreement is missing. Installation cannot continue safely."
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
    if shutil.which("npm") is None:
        print(
            "npm not found; skipping desktop package install. Install Node.js for the desktop UI."
        )
        return
    print("Installing desktop UI dependencies...")
    run(["npm", "install"], cwd=DESKTOP_DIR)


def install_playwright_browser(python_exe: Path) -> None:
    print("Preparing Playwright browser runtime...")
    try:
        run([str(python_exe), "-m", "playwright", "install", "chromium"])
    except subprocess.CalledProcessError:
        print(
            "Playwright Chromium install failed. Universal AI will still run; browser automation can be repaired later."
        )


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
        print("Universal AI is running. Press Ctrl+C here to stop the backend.")
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
