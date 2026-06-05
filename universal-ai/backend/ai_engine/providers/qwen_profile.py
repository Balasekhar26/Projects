from __future__ import annotations

from typing import Any


def qwen_profile(installed_models: list[str] | None = None) -> dict[str, Any]:
    installed_models = installed_models or []
    matches = [model for model in installed_models if "qwen" in model.lower()]
    return {
        "key": "qwen",
        "provider": "ollama/local",
        "roles": ["coding", "vision", "web_extraction", "general"],
        "installed_models": matches,
        "status": "ready" if matches else "missing",
        "install_hint": "ollama pull qwen2.5-coder:3b for coding or a Qwen vision model for screenshots.",
    }
