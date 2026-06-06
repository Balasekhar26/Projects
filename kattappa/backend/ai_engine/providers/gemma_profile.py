from __future__ import annotations

from typing import Any


def gemma_profile(installed_models: list[str] | None = None) -> dict[str, Any]:
    installed_models = installed_models or []
    matches = [model for model in installed_models if "gemma" in model.lower()]
    return {
        "key": "gemma",
        "provider": "ollama/local",
        "roles": ["general", "reasoning", "writing", "agentic"],
        "installed_models": matches,
        "status": "ready" if matches else "missing",
        "install_hint": "ollama pull gemma3:4b or another locally licensed Gemma variant.",
    }
