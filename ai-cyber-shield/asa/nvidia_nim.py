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
        return self.config.nvidia_enabled

    def incident_guidance(self, events: list[dict[str, Any]]) -> str | None:
        if not self.available():
            return None

        recent_events = summarize_events(events)
        if not recent_events:
            return None

        if not self._api_key():
            return self._local_defensive_triage(events)

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

    def _local_defensive_triage(self, events: list[dict[str, Any]]) -> str:
        high_critical = [e for e in events if e.get("level") in {"high", "critical"}]
        advice = [
            "### Local Defensive Triage Advice (Offline Mode)",
            "",
            "**Assessed Threat Risk Level:** " + ("HIGH/CRITICAL" if high_critical else "LOW/MEDIUM"),
            "",
            "**Observations:**",
        ]
        if not events:
            advice.append("- No recent security event indicators present in the logs.")
        else:
            components = sorted(list({e.get("component", "unknown") for e in events}))
            for comp in components:
                advice.append(f"- Active telemetry analyzed from component: `{comp}`")
            
            suspicious = [e for e in events if any(word in str(e).lower() for word in ["suspicious", "fail", "blocked"])]
            if suspicious:
                advice.append("- Risky process, port connection, or baseline deviation detected.")
        
        advice.extend([
            "",
            "**Immediate Defensive Steps:**",
            "1. **IP Isolation:** For suspicious outbound connections, immediately block the remote IP address via localized firewall policies or the blocklist.",
            "2. **Process Inspection:** Verify executable paths and verify signatures of flagged background processes.",
            "3. **Hardening Checks:** Run `hardening-audit` to inspect for local system vulnerabilities.",
        ])
        return "\n".join(advice)


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
