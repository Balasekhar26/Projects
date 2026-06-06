from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.config import load_config
from backend.core.free_stack import free_stack_report
from backend.core.memory import memory
from backend.core.source_policy import source_first_policy


PYTHON_PACKAGES = {
    "langgraph": "langgraph",
    "chromadb": "chromadb",
    "playwright": "playwright",
    "pyautogui": "pyautogui",
    "mss": "mss",
    "pytesseract": "pytesseract",
    "faster_whisper": "faster-whisper",
    "piper": "piper-tts",
    "openwakeword": "openwakeword",
    "pywinauto": "pywinauto",
}

PACKAGE_SOURCE_NOTES = {
    "langgraph": "Open-source Python agent/workflow framework; use only as graph adapter, not as Kattappa's identity.",
    "chromadb": "Open-source local vector database; use as replaceable semantic memory storage.",
    "playwright": "Open-source browser automation framework; use as replaceable browser-control adapter.",
    "pyautogui": "Open-source desktop input library; use only behind approval-gated operator modes.",
    "mss": "Open-source screen capture utility; use only for local screenshots.",
    "pytesseract": "Open-source Python bridge to Tesseract OCR; keep OCR adapter replaceable.",
    "faster_whisper": "Open-source Whisper inference implementation; local STT adapter only.",
    "piper-tts": "Open-source local TTS engine; local voice adapter only.",
    "openwakeword": "Open-source wake-word package; local wake adapter only.",
    "pywinauto": "Open-source Windows UI Automation library; approval-gated desktop adapter only.",
}

MANUAL_CAPABILITIES = {
    "ollama": "Install Ollama for Windows, then restart Kattappa AI OS.",
    "tesseract": "Install Tesseract OCR for Windows and add it to PATH.",
}


@dataclass(frozen=True)
class InstallStep:
    label: str
    command: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "command": self.command}


def build_missing_install_plan() -> dict[str, Any]:
    report = free_stack_report()
    config = load_config()
    python_exe = str(config.root / "ai_system_env" / "Scripts" / "python.exe")
    steps: list[InstallStep] = []
    manual_steps: list[str] = []

    for item in report["capabilities"]:
        if item["installed"]:
            continue
        key = item["key"]
        if key in PYTHON_PACKAGES:
            package = PYTHON_PACKAGES[key]
            steps.append(
                InstallStep(
                    label=f"Inspect and install {item['name']} Python package",
                    command=[python_exe, "-m", "pip", "install", package],
                )
            )
            if key == "playwright":
                steps.append(
                    InstallStep(
                        label="Install Playwright Chromium browser",
                        command=[python_exe, "-m", "playwright", "install", "chromium"],
                    )
                )
        elif key in MANUAL_CAPABILITIES:
            manual_steps.append(MANUAL_CAPABILITIES[key])

    ollama_exe = "ollama"
    for model in report["models"]["missing_recommended"]:
        steps.append(
            InstallStep(
                label=f"Pull inspectable local Ollama model profile {model}",
                command=[ollama_exe, "pull", model],
            )
        )

    return {
        "mode": "approval_required",
        "summary": f"{len(steps)} automatic install steps, {len(manual_steps)} manual steps.",
        "steps": [step.to_dict() for step in steps],
        "manual_steps": manual_steps,
        "free_local_only": True,
        "source_first": source_first_policy(),
        "source_notes": PACKAGE_SOURCE_NOTES,
    }


def request_missing_install_approval() -> dict[str, Any]:
    plan = build_missing_install_plan()
    if not plan["steps"] and not plan["manual_steps"]:
        return {"status": "ready", "message": "All required free/local capabilities are already ready.", "plan": plan}
    approval_id = memory.create_approval(
        action=(
            "Install missing free/local Kattappa AI OS capabilities. "
            f"{plan['summary']} Automatic commands will run only after approval."
        ),
        risk="medium",
    )
    memory.create_install_job(approval_id, json.dumps(plan))
    return {
        "status": "approval_required",
        "approval_id": approval_id,
        "message": "Approval created. Click Approve in the approval panel to install missing capabilities.",
        "plan": plan,
    }


def run_approved_install_job(approval_id: str) -> dict[str, Any]:
    approval = memory.get_approval(approval_id)
    job = memory.get_install_job(approval_id)
    if job is None:
        return {"status": "not_install_job", "message": "No install job is attached to this approval."}
    if approval is None:
        memory.update_install_job(approval_id, "failed", "Approval was not found.")
        return {"status": "failed", "message": "Approval was not found."}
    if approval["status"] != "approved":
        return {"status": "waiting_for_approval", "message": "Install job is waiting for approval."}

    plan = json.loads(job["plan"])
    results: list[dict[str, Any]] = []
    for step in plan["steps"]:
        command = step["command"]
        if not _command_is_allowlisted(command):
            results.append({"label": step["label"], "status": "blocked", "message": "Command is not allowlisted."})
            continue
        try:
            completed = subprocess.run(
                command,
                cwd=load_config().root,
                capture_output=True,
                text=True,
                timeout=900,
            )
            results.append(
                {
                    "label": step["label"],
                    "status": "done" if completed.returncode == 0 else "failed",
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                }
            )
        except Exception as exc:
            results.append({"label": step["label"], "status": "failed", "message": str(exc)})

    status = "done" if all(item["status"] == "done" for item in results) else "partial"
    if not results and plan["manual_steps"]:
        status = "manual_required"
    memory.update_install_job(approval_id, status, json.dumps({"results": results, "manual_steps": plan["manual_steps"]}))
    return {"status": status, "approval_id": approval_id, "results": results, "manual_steps": plan["manual_steps"]}


def _command_is_allowlisted(command: list[str]) -> bool:
    if len(command) >= 5 and Path(command[0]).name.lower() == "python.exe" and command[1:4] == ["-m", "pip", "install"]:
        return command[4] in set(PYTHON_PACKAGES.values())
    if len(command) == 5 and Path(command[0]).name.lower() == "python.exe" and command[1:] == [
        "-m",
        "playwright",
        "install",
        "chromium",
    ]:
        return True
    if len(command) == 3 and command[0] == "ollama" and command[1] == "pull":
        return command[2] in set(free_stack_report()["models"]["recommended"].values())
    return False
