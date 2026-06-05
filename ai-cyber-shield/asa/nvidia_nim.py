from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .config import ASAConfig


class NvidiaNimAdvisor:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config

    def available(self) -> bool:
        return self.config.nvidia_enabled and bool(self._api_key())

    def incident_guidance(self, events: list[dict[str, Any]]) -> str | None:
        if not self.available():
            return None

        recent_events = summarize_events(events)
        if not recent_events:
            return None

        prompt = (
            "You are a defensive security incident triage assistant. "
            "Analyze only the event summary below. Do not suggest retaliation, scanning third-party "
            "systems, exploit code, credential theft, persistence, or destructive actions. "
            "Return concise Markdown with: risk level, likely causes, immediate containment steps, "
            "evidence to preserve, and follow-up hardening.\n\n"
            f"Event summary:\n{recent_events}"
        )

        payload = {
            "model": self.config.nvidia_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You provide defensive-only cybersecurity guidance.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": self.config.nvidia_max_tokens,
            "stream": False,
        }
        try:
            data = self._post_json("/v1/chat/completions", payload)
        except Exception as exc:
            return f"_NVIDIA NIM guidance unavailable: {exc}_"

        choices = data.get("choices") or [{}]
        content = choices[0].get("message", {}).get("content", "")
        return str(content).strip() or None

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.config.nvidia_base_url.rstrip("/") + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.nvidia_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        return json.loads(raw) if raw else {}

    def _api_key(self) -> str:
        return os.getenv(self.config.nvidia_api_key_env, "") or os.getenv("NVIDIA_API_KEY", "")


def summarize_events(events: list[dict[str, Any]], limit: int = 20) -> str:
    rows: list[str] = []
    for event in events[-limit:]:
        fields = event.get("fields", {})
        score = fields.get("score") if isinstance(fields, dict) else None
        score_text = f" score={score}" if score is not None else ""
        rows.append(
            "- "
            f"{event.get('ts', 'unknown')} "
            f"{event.get('level', 'unknown')} "
            f"{event.get('component', 'unknown')}/"
            f"{event.get('event', 'unknown')}: "
            f"{event.get('message', '')}{score_text}"
        )
    return "\n".join(rows)
