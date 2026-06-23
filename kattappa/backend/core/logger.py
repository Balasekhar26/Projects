from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.core.config import load_config


def log_event(event: str, metadata: dict | None = None) -> None:
    config = load_config()
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    path = config.logs_dir / "agent.log"
    timestamp = datetime.now().isoformat(timespec="seconds")
    meta_str = f" | {metadata}" if metadata else ""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {event}{meta_str}\n")


def read_log(limit: int = 100) -> list[str]:
    path = load_config().logs_dir / "agent.log"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()[-limit:]
