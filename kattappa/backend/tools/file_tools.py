from __future__ import annotations

from pathlib import Path

from backend.core.config import load_config
from backend.core.safety import classify_risk


def _safe_path(path: str) -> Path:
    config = load_config()
    target = (config.root / path).resolve()
    if not str(target).startswith(str(config.root)):
        raise PermissionError("Path escapes AI_System root")
    return target


def read_text(path: str, limit: int = 20000) -> str:
    target = _safe_path(path)
    return target.read_text(encoding="utf-8")[:limit]


def write_text_preview(path: str, content: str) -> dict[str, object]:
    risk = classify_risk(f"write file {path}")
    return {
        "approval_required": True,
        "risk": risk.level,
        "path": str(_safe_path(path)),
        "preview": content[:2000],
        "message": "File writes require approval.",
    }
