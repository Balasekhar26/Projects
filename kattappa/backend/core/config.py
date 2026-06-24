from __future__ import annotations

import os
import platform
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
    screen_capture_enabled: bool
    guidance_overlay_enabled: bool
    teach_mode_enabled: bool
    screenshots_dir: Path
    audio_dir: Path
    logs_dir: Path
    workspace_dir: Path
    hardware_profile: str
    context_budget: int


def _load_yaml() -> dict[str, Any]:
    path = BACKEND_ROOT / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _uses_app_data_root() -> bool:
    return bool(os.getenv("KATTAPPA_DATA_DIR")) or platform.system().lower() in {"darwin", "windows"}


def runtime_data_root() -> Path:
    raw = os.getenv("KATTAPPA_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    system = platform.system().lower()
    if system == "darwin":
        return (Path.home() / "Library" / "Application Support" / "Kattappa AI OS").resolve()
    if system == "windows":
        return (Path.home() / "AppData" / "Local" / "Kattappa AI OS").resolve()
    return ROOT


def _resolve_runtime_path(value: str | None, fallback: str) -> Path:
    path = Path(value or fallback).expanduser()
    if path.is_absolute():
        return path.resolve()
    base = runtime_data_root() if _uses_app_data_root() else ROOT
    return (base / path).resolve()


def legacy_runtime_path(value: str | None, fallback: str) -> Path:
    path = Path(value or fallback).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (ROOT / path).resolve()


def _detect_hardware_defaults_profile() -> tuple[str, str, str, str, str, int]:
    from backend.core.adaptive_runtime import HardwareProfiler, PerformanceProfile, AdaptiveContext
    try:
        hw = HardwareProfiler.get_profile()
        profile = PerformanceProfile.resolve_profile(hw)
    except Exception:
        profile = "BALANCED"
        
    limits = AdaptiveContext.get_limits(profile)
    budget = limits["max_context_tokens"]
    
    if profile == "ECO":
        # ECO mode: small, fast footprint models
        return "qwen2.5:0.5b", "qwen2.5-coder:3b", "qwen2.5-coder:3b", "qwen2.5-coder:3b", profile, budget
    elif profile == "BALANCED":
        # BALANCED mode: qwen3 4b + coder 3b
        return "qwen3:4b", "qwen2.5-coder:3b", "qwen2.5-coder:3b", "qwen2.5-coder:3b", profile, budget
    elif profile == "PERFORMANCE":
        # PERFORMANCE mode: qwen3 4b + coder 3b + mistral 7b
        return "qwen3:4b", "mistral:latest", "qwen2.5-coder:3b", "mistral:latest", profile, budget
    else:  # BEAST
        # BEAST mode: qwen3 4b + coder 3b + mistral 7b
        return "qwen3:4b", "mistral:latest", "qwen2.5-coder:3b", "mistral:latest", profile, budget


_config_override = None


def load_config() -> BackendConfig:
    import sys
    mod = sys.modules.get("backend.core.config")
    if mod and mod.load_config is not load_config:
        return mod.load_config()

    if _config_override is not None:
        return _config_override() if callable(_config_override) else _config_override

    data = _load_yaml()
    models = data.get("models", {})
    memory = data.get("memory", {})
    safety = data.get("safety", {})
    paths = data.get("paths", {})
    ollama = data.get("ollama", {})

    d_fast_gen, d_power, d_coder, d_reasoning, profile, budget = _detect_hardware_defaults_profile()

    return BackendConfig(
        root=ROOT,
        backend_root=BACKEND_ROOT,
        ollama_host=os.getenv(
            "OLLAMA_HOST", ollama.get("host", "http://127.0.0.1:11434")
        ),
        model_map={
            "fast": os.getenv("KATTAPPA_MODEL_FAST", models.get("fast", d_fast_gen)),
            "general": os.getenv(
                "KATTAPPA_MODEL_GENERAL", models.get("general", d_fast_gen)
            ),
            "power": os.getenv("KATTAPPA_MODEL_POWER", models.get("power", d_power)),
            "coder": os.getenv(
                "KATTAPPA_MODEL_CODER", models.get("coder", d_coder)
            ),
            "vision": os.getenv(
                "KATTAPPA_MODEL_VISION", models.get("vision", "qwen3-vl:8b")
            ),
            "reasoning": os.getenv(
                "KATTAPPA_MODEL_REASONING", models.get("reasoning", d_reasoning)
            ),
        },
        chroma_path=_resolve_runtime_path(
            memory.get("chroma_path"), "backend/memory/chroma"
        ),
        sqlite_path=_resolve_runtime_path(
            memory.get("sqlite_path"), "backend/memory/sqlite/kattappa_ai_os.db"
        ),
        memory_collection=memory.get("collection", "kattappa_memory"),
        shell_enabled=_bool_env(
            "KATTAPPA_SHELL_ENABLED", bool(safety.get("shell_enabled", False))
        ),
        desktop_enabled=_bool_env(
            "KATTAPPA_DESKTOP_ENABLED", bool(safety.get("desktop_enabled", False))
        ),
        screen_capture_enabled=_bool_env(
            "KATTAPPA_SCREEN_CAPTURE_ENABLED",
            bool(
                safety.get(
                    "screen_capture_enabled",
                    platform.system().lower() != "darwin",
                )
            ),
        ),
        guidance_overlay_enabled=_bool_env(
            "KATTAPPA_GUIDANCE_OVERLAY_ENABLED",
            bool(safety.get("guidance_overlay_enabled", True)),
        ),
        teach_mode_enabled=_bool_env(
            "KATTAPPA_TEACH_MODE_ENABLED", bool(safety.get("teach_mode_enabled", True))
        ),
        screenshots_dir=_resolve_runtime_path(
            paths.get("screenshots"), "backend/data/screenshots"
        ),
        audio_dir=_resolve_runtime_path(paths.get("audio"), "backend/data/audio"),
        logs_dir=_resolve_runtime_path(paths.get("logs"), "backend/data/logs"),
        workspace_dir=_resolve_runtime_path(paths.get("workspace"), "workspace"),
        hardware_profile=profile,
        context_budget=budget,
    )

JARVIS_MODE = True


_security_config_cached = None

def load_security_config() -> dict:
    global _security_config_cached
    import copy
    if _security_config_cached is not None:
        return copy.deepcopy(_security_config_cached)

    import yaml
    config_path = ROOT / "backend" / "config" / "security_config.yaml"
    if not config_path.exists():
        config_path = BACKEND_ROOT / "config" / "security_config.yaml"
    
    if config_path.exists():
        try:
            _security_config_cached = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            _security_config_cached = {}
    else:
        _security_config_cached = {}
        
    return copy.deepcopy(_security_config_cached)

