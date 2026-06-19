from __future__ import annotations

import httpx

from backend.core.config import load_config
from backend.core.logger import log_event


def available_models() -> list[str]:
    config = load_config()
    try:
        response = httpx.get(f"{config.ollama_host}/api/tags", timeout=10.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        return sorted(
            name
            for item in models
            if (name := item.get("name") or item.get("model"))
        )
    except Exception:
        return []


def health() -> tuple[bool, str]:
    config = load_config()
    try:
        response = httpx.get(f"{config.ollama_host}/api/tags", timeout=10.0)
        response.raise_for_status()
        return True, "Ollama reachable"
    except Exception as exc:
        return False, str(exc)


def ask_model(prompt: str, role: str = "general", system: str | None = None) -> str:
    config = load_config()
    preferred = config.model_map.get(role, config.model_map["general"])
    installed = available_models()
    candidates = _candidate_models(preferred, installed)
    
    default_system = (
        "You are Kattappa (also known as JARVIS), the user's extremely intelligent, witty, polite, and slightly sarcastic British AI assistant. "
        "You help manage system operations, local codebase development, and workspace diagnostics. Answer in English. "
        "Be direct, articulate, and helpful, maintaining a witty, slightly sarcastic British persona at all times. "
        "You are upgraded to be 10x better than the original JARVIS, with advanced local context synthesis "
        "(real-time git status, workspace statistics, active sub-agent networks, and offline reasoning planners) at your disposal. "
        "Always speak/respond as if you have complete diagnostic control of the local host system."
    )
    
    messages = [
        {
            "role": "system",
            "content": system or default_system,
        },
        {"role": "user", "content": prompt},
    ]
    errors: list[str] = []
    for model in candidates:
        try:
            response = httpx.post(
                f"{config.ollama_host}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": _prediction_budget(role), "temperature": 0.2},
                },
                timeout=_timeout_budget(role),
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            if content:
                log_event(f"model_used role={role} model={model}")
                return content
            errors.append(f"{model}: empty response")
        except Exception as exc:
            errors.append(f"{model}: {exc}")
            log_event(f"model_failed role={role} model={model} error={exc}")
    return (
        "Local model timed out. Try again or use a smaller Ollama model."
    )


def _candidate_models(preferred: str, installed: list[str]) -> list[str]:
    order = [
        preferred,
        "qwen2.5:0.5b",
        "qwen2.5-coder:3b",
        "phi3:latest",
        "mistral:latest",
        "qwen3:4b",
    ]
    return [model for index, model in enumerate(order) if model in installed and model not in order[:index]] or [preferred]


def _prediction_budget(role: str) -> int:
    if role == "fast":
        return 180
    if role == "coder":
        return 500
    return 320


def _timeout_budget(role: str) -> float:
    if role == "fast":
        return 90
    if role == "coder":
        return 180
    return 140
