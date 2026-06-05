from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    root: Path
    ollama_host: str
    planner_model: str
    coder_model: str
    fast_model: str
    heavy_model: str
    memory_dir: Path
    memory_collection: str
    allow_shell: bool
    allow_desktop_control: bool
    allow_browser_control: bool
    screenshots_dir: Path


def _read_yaml() -> dict[str, Any]:
    settings_file = ROOT / "config" / "settings.yaml"
    if not settings_file.exists():
        return {}
    return yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    data = _read_yaml()
    models = data.get("models", {})
    memory = data.get("memory", {})
    safety = data.get("safety", {})
    vision = data.get("vision", {})

    memory_dir = Path(os.getenv("AI_SYSTEM_MEMORY_DIR", memory.get("persist_directory", "memory/chroma")))
    screenshots_dir = Path(vision.get("screenshots_dir", "memory/screenshots"))

    return Settings(
        root=ROOT,
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        planner_model=os.getenv("AI_SYSTEM_MODEL_PLANNER", models.get("planner", "qwen3:4b")),
        coder_model=os.getenv("AI_SYSTEM_MODEL_CODER", models.get("coder", "qwen2.5-coder:3b")),
        fast_model=os.getenv("AI_SYSTEM_MODEL_FAST", models.get("fast", "phi3")),
        heavy_model=models.get("heavy_reasoning", "deepseek-r1:8b"),
        memory_dir=(ROOT / memory_dir).resolve(),
        memory_collection=memory.get("collection", "ai_system_memory"),
        allow_shell=_bool_env("AI_SYSTEM_ALLOW_SHELL", bool(safety.get("allow_shell", False))),
        allow_desktop_control=bool(safety.get("allow_desktop_control", False)),
        allow_browser_control=bool(safety.get("allow_browser_control", True)),
        screenshots_dir=(ROOT / screenshots_dir).resolve(),
    )
