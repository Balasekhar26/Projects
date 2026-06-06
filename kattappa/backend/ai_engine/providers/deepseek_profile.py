from __future__ import annotations

from typing import Any


def deepseek_profile(installed_models: list[str] | None = None) -> dict[str, Any]:
    installed_models = installed_models or []
    matches = [model for model in installed_models if "deepseek" in model.lower()]
    return {
        "key": "deepseek",
        "provider": "ollama/local",
        "roles": ["reasoning", "coding"],
        "installed_models": matches,
        "status": "ready" if matches else "missing",
        "install_hint": "ollama pull deepseek-coder or another locally runnable DeepSeek variant.",
    }
