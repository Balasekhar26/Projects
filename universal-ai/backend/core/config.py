from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
load_dotenv(BACKEND_ROOT / ".env")


@dataclass(frozen=True)
class BackendConfig:
    root: Path
    backend_root: Path
    ollama_host: str
    model_map: dict[str, str]
    chroma_path: Path
    sqlite_path: Path
    memory_collection: str
    shell_enabled: bool
    desktop_enabled: bool
    guidance_overlay_enabled: bool
    teach_mode_enabled: bool
    screenshots_dir: Path
    audio_dir: Path
    logs_dir: Path
    workspace_dir: Path


def _load_yaml() -> dict[str, Any]:
    path = BACKEND_ROOT / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def load_config() -> BackendConfig:
    data = _load_yaml()
    models = data.get("models", {})
    memory = data.get("memory", {})
    safety = data.get("safety", {})
    paths = data.get("paths", {})
    ollama = data.get("ollama", {})

    return BackendConfig(
        root=ROOT,
        backend_root=BACKEND_ROOT,
        ollama_host=os.getenv(
            "OLLAMA_HOST", ollama.get("host", "http://127.0.0.1:11434")
        ),
        model_map={
            "fast": os.getenv("SEKHAR_MODEL_FAST", models.get("fast", "qwen3:4b")),
            "general": os.getenv(
                "SEKHAR_MODEL_GENERAL", models.get("general", "qwen3:4b")
            ),
            "power": os.getenv("SEKHAR_MODEL_POWER", models.get("power", "qwen3:30b")),
            "coder": os.getenv(
                "SEKHAR_MODEL_CODER", models.get("coder", "qwen2.5-coder:3b")
            ),
            "vision": os.getenv(
                "SEKHAR_MODEL_VISION", models.get("vision", "qwen3-vl:8b")
            ),
            "reasoning": os.getenv(
                "SEKHAR_MODEL_REASONING", models.get("reasoning", "gpt-oss:20b")
            ),
        },
        chroma_path=(
            ROOT / memory.get("chroma_path", "backend/memory/chroma")
        ).resolve(),
        sqlite_path=(
            ROOT / memory.get("sqlite_path", "backend/memory/sqlite/sekhar_ai_os.db")
        ).resolve(),
        memory_collection=memory.get("collection", "sekhar_memory"),
        shell_enabled=_bool_env(
            "SEKHAR_SHELL_ENABLED", bool(safety.get("shell_enabled", False))
        ),
        desktop_enabled=_bool_env(
            "SEKHAR_DESKTOP_ENABLED", bool(safety.get("desktop_enabled", False))
        ),
        guidance_overlay_enabled=_bool_env(
            "SEKHAR_GUIDANCE_OVERLAY_ENABLED",
            bool(safety.get("guidance_overlay_enabled", True)),
        ),
        teach_mode_enabled=_bool_env(
            "SEKHAR_TEACH_MODE_ENABLED", bool(safety.get("teach_mode_enabled", True))
        ),
        screenshots_dir=(
            ROOT / paths.get("screenshots", "backend/data/screenshots")
        ).resolve(),
        audio_dir=(ROOT / paths.get("audio", "backend/data/audio")).resolve(),
        logs_dir=(ROOT / paths.get("logs", "backend/data/logs")).resolve(),
        workspace_dir=(ROOT / paths.get("workspace", "workspace")).resolve(),
    )
