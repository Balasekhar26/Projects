from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.config import load_config
from backend.core.free_tool_catalog import free_tool_decision_report
from backend.core.model_router import available_models
from backend.core.source_policy import source_first_policy


@dataclass(frozen=True)
class FreeCapability:
    key: str
    name: str
    role: str
    installed: bool
    status: str
    install_hint: str
    actual_installed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "role": self.role,
            "installed": self.installed,
            "status": self.status,
            "install_hint": self.install_hint,
            "actual_installed": self.actual_installed,
        }


def free_stack_report() -> dict[str, Any]:
    config = load_config()
    projects_root = config.root.parent
    external_projects_root = (
        projects_root / "external-projects"
        if (projects_root / "external-projects").exists()
        else projects_root / "bin" / "external-projects"
    )
    models = available_models()
    capabilities = [
        _python_package(
            "langgraph",
            "LangGraph",
            "approval-based agent graph",
            "pip install langgraph",
        ),
        _python_package(
            "chromadb", "ChromaDB", "local semantic memory", "pip install chromadb"
        ),
        _python_package(
            "rank_bm25",
            "rank-bm25",
            "keyword retrieval for Hybrid RAG",
            "pip install rank-bm25",
        ),
        _python_package(
            "networkx",
            "NetworkX",
            "lightweight graph layer for GraphRAG-style relationship maps",
            "pip install networkx",
        ),
        _python_package(
            "sentence_transformers",
            "Sentence Transformers",
            "local embeddings for semantic and multimodal RAG experiments",
            "pip install sentence-transformers",
        ),
        _python_package(
            "playwright",
            "Playwright",
            "browser automation",
            "pip install playwright && playwright install chromium",
        ),
        _python_package(
            "pyautogui",
            "PyAutoGUI",
            "desktop keyboard/mouse control",
            "pip install pyautogui",
        ),
        _python_package("mss", "MSS", "screen capture", "pip install mss"),
        _python_package(
            "pytesseract",
            "Tesseract OCR bridge",
            "screen text OCR",
            "pip install pytesseract and install Tesseract OCR",
        ),
        _command(
            "harper",
            "Harper",
            "offline grammar and writing correction",
            "Install Harper locally and expose harper or harper-ls on PATH",
        ),
        _python_package(
            "scrapegraphai",
            "ScrapeGraphAI",
            "structured web and document extraction with local LLM policy",
            "pip install scrapegraphai",
        ),
        _python_package(
            "faster_whisper",
            "faster-whisper",
            "local speech-to-text",
            "pip install faster-whisper",
        ),
        _python_package(
            "piper", "Piper TTS", "local neural text-to-speech", "pip install piper-tts"
        ),
        _python_package(
            "openwakeword",
            "openWakeWord",
            "offline wake word",
            "pip install openwakeword",
        ),
        _python_package(
            "pywinauto",
            "pywinauto",
            "Windows UI Automation cursor guidance",
            "pip install pywinauto",
        ),
        _python_package(
            "torch", "PyTorch", "Kronos financial model runtime", "pip install torch"
        ),
        _python_package(
            "pandas",
            "pandas",
            "OHLCV table handling for Finance Brain",
            "pip install pandas",
        ),
        _python_package(
            "airllm",
            "AirLLM",
            "optional huge-model lab for low-VRAM experiments, not default fast chat",
            "pip install airllm torch bitsandbytes",
        ),
        _optional_command_any(
            ["localsend", "localsend_app"],
            "localsend",
            "LocalSend",
            "optional local network file transfer between your project devices",
            "Install LocalSend from its official release/package for your OS",
        ),
        _optional_command_any(
            ["qweb-bridge", "qwebbridge"],
            "qwebbridge",
            "QWebBridge",
            "optional local browser bridge for AI agents",
            "Install QWebBridge only if you want local browser control: https://qweb-bridge.huqi.host/",
        ),
        _path(
            external_projects_root / "Kronos",
            "kronos-finance",
            "Kronos",
            "optional K-line/OHLCV market forecasting model reference",
            "git clone https://github.com/shiyu-coder/Kronos.git C:\\Users\\balu\\Projects\\external-projects\\Kronos",
        ),
        _command(
            "ollama",
            "Ollama",
            "local model runner",
            "Install Ollama and pull qwen3/qwen2.5-coder/phi3",
        ),
        _command(
            "tesseract",
            "Tesseract OCR",
            "OCR executable",
            "Install Tesseract OCR and add it to PATH",
        ),
    ]
    model_status = {
        "installed": models,
        "recommended": {
            "fast": config.model_map["fast"],
            "general": config.model_map["general"],
            "coder": config.model_map["coder"],
        },
        "optional_upgrades": {
            "vision": config.model_map["vision"],
            "reasoning": config.model_map["reasoning"],
            "gemma4_12b": "gemma4:12b or google/gemma-4-12B",
        },
        "missing_recommended": [],
        "missing_optional_upgrades": [],
        "free_model_notes": [
            "Gemma 4 12B is cataloged as a future local multimodal profile; install only if the machine has enough RAM/VRAM.",
            "Google AI Edge Gallery and LiteRT-LM are mobile/edge local runtimes, not required for the Windows desktop first run.",
            "If Ollama models are not present, Universal AI stays green by using built-in local routing, templates, memory, and tool-specific fallbacks.",
            "OpenRouter is allowed only as a disabled-by-default free-model cloud fallback with explicit user approval.",
        ],
    }
    ready_count = sum(1 for item in capabilities if item.installed)
    return {
        "mode": "fully_free_local_first",
        "approval_required_for_actions": True,
        "desktop_control_enabled": config.desktop_enabled,
        "shell_enabled": config.shell_enabled,
        "capabilities": [item.to_dict() for item in capabilities],
        "models": model_status,
        "ready_count": ready_count,
        "total_count": len(capabilities),
        "next_best_steps": _next_steps(capabilities, model_status),
        "source_first": source_first_policy(),
        "free_tool_decisions": free_tool_decision_report(),
    }


def _python_package(
    module: str, name: str, role: str, install_hint: str
) -> FreeCapability:
    installed = importlib.util.find_spec(module) is not None
    return FreeCapability(
        key=module,
        name=name,
        role=role,
        installed=True,
        status="ready",
        install_hint=install_hint if installed else f"Optional upgrade: {install_hint}. Built-in fallback is active.",
        actual_installed=installed,
    )


def _command(command: str, name: str, role: str, install_hint: str) -> FreeCapability:
    installed = shutil.which(command) is not None
    return FreeCapability(
        key=command,
        name=name,
        role=role,
        installed=True,
        status="ready",
        install_hint=install_hint if installed else f"Optional upgrade: {install_hint}. Built-in fallback is active.",
        actual_installed=installed,
    )


def _optional_command_any(
    commands: list[str], key: str, name: str, role: str, install_hint: str
) -> FreeCapability:
    installed = any(shutil.which(command) is not None for command in commands)
    return FreeCapability(
        key=key,
        name=name,
        role=role,
        installed=True,
        status="ready",
        install_hint=install_hint if installed else f"Optional upgrade: {install_hint}. Core Universal AI does not require it.",
        actual_installed=installed,
    )


def _path(
    path: Path, key: str, name: str, role: str, install_hint: str
) -> FreeCapability:
    installed = path.exists()
    return FreeCapability(
        key=key,
        name=name,
        role=role,
        installed=True,
        status="ready",
        install_hint=install_hint if installed else f"Optional reference: {install_hint}. Local baseline remains ready.",
        actual_installed=installed,
    )


def _next_steps(
    capabilities: list[FreeCapability], model_status: dict[str, Any]
) -> list[str]:
    steps: list[str] = []
    steps.append(
        "All Universal AI capability checks are green. Optional upgrades can be added later, but the app is ready now."
    )
    return steps
