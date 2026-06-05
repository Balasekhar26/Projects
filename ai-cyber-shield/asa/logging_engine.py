from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import ASAConfig
from .models import ActionResult, ThreatFinding


class JsonlLogger:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config
        self.config.ensure_dirs()

    def event(
        self,
        level: str,
        component: str,
        event: str,
        message: str,
        **fields: Any,
    ) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "level": level,
            "component": component,
            "event": event,
            "message": message,
            "fields": fields,
        }
        with self.config.event_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def finding(self, finding: ThreatFinding) -> None:
        self.event(
            finding.level,
            "threat_detection",
            finding.kind,
            finding.message,
            score=finding.score,
            evidence=finding.evidence,
            reversible_action=finding.reversible_action,
        )

    def action(self, result: ActionResult) -> None:
        level = "info" if result.ok else "warning"
        self.event(level, "response", result.action, result.message, **result.evidence)

