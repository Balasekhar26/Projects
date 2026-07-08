from __future__ import annotations

from pathlib import Path

from ai_system.core.config import load_settings


def ensure_runtime_dirs() -> None:
    settings = load_settings()
    for path in [
        settings.memory_dir,
        settings.screenshots_dir,
        settings.root / "logs",
        settings.root / "conversations",
        settings.root / "workflows",
        settings.root / "workspace",
    ]:
        path.mkdir(parents=True, exist_ok=True)
