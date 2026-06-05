from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import httpx
import ollama

from ai_system.core.config import Settings


@dataclass
class LocalLLM:
    settings: Settings

    def __post_init__(self) -> None:
        self.client = ollama.Client(host=self.settings.ollama_host)

    def health(self) -> tuple[bool, str]:
        try:
            response = httpx.get(f"{self.settings.ollama_host}/api/tags", timeout=5)
            response.raise_for_status()
            return True, "Ollama is reachable"
        except Exception as exc:
            return False, f"Ollama is not reachable: {exc}"

    def list_models(self) -> list[str]:
        try:
            data = self.client.list()
        except Exception:
            return []
        models = data.get("models", []) if isinstance(data, dict) else getattr(data, "models", [])
        names: list[str] = []
        for model in models:
            if isinstance(model, dict):
                names.append(model.get("name") or model.get("model") or "")
            else:
                names.append(getattr(model, "model", "") or getattr(model, "name", ""))
        return sorted(name for name in names if name)

    def choose_model(self, mode: str = "planner") -> str:
        if mode == "coder":
            return self.settings.coder_model
        if mode == "fast":
            return self.settings.fast_model
        return self.settings.planner_model

    def chat(self, messages: Iterable[dict[str, str]], mode: str = "planner") -> str:
        model = self.choose_model(mode)
        response = self.client.chat(model=model, messages=list(messages))
        message = response.get("message", {}) if isinstance(response, dict) else response.message
        return message.get("content", "") if isinstance(message, dict) else message.content
