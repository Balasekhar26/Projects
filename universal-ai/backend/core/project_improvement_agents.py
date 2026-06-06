from __future__ import annotations

import json
from typing import Any

from backend.core.config import load_config


def project_improvement_agents() -> dict[str, Any]:
    path = load_config().root / "config" / "project_improvement_agents.json"
    if not path.exists():
        return {
            "mode": "missing_registry",
            "shared_registry": "docs/SHARED_IMPROVEMENTS.md",
            "projects": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))
