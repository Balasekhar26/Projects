from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ASAConfig
from .nvidia_nim import NvidiaNimAdvisor


class ReportWriter:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config
        self.config.ensure_dirs()

    def write(self) -> Path:
        events = self._events()
        severity_counts = Counter(str(event.get("level", "unknown")) for event in events)
        kind_counts = Counter(str(event.get("event", "unknown")) for event in events)
        report_path = self.config.reports_dir / f"asa-incident-{_stamp()}.md"

        lines = [
            "# ASA Incident Report",
            "",
            f"- Generated: {_now()}",
            f"- Event log: {self.config.event_log}",
            f"- Baseline: {self.config.baseline_file}",
            "",
            "## Severity Counts",
            "",
        ]
        lines.extend(f"- {level}: {count}" for level, count in severity_counts.most_common())
        lines.extend(["", "## Event Counts", ""])
        lines.extend(f"- {event}: {count}" for event, count in kind_counts.most_common())
        lines.extend(["", "## Recent Findings", ""])
        recent = [
            event
            for event in events
            if event.get("component") in {"threat_detection", "response"}
        ][-20:]
        if recent:
            for event in recent:
                lines.append(
                    f"- {event.get('ts')} {event.get('level')} "
                    f"{event.get('event')}: {event.get('message')}"
                )
        else:
            lines.append("- No findings recorded.")

        guidance = NvidiaNimAdvisor(self.config).incident_guidance(recent)
        if guidance:
            lines.extend(["", "## NVIDIA NIM Defensive Analysis", "", guidance])

        lines.extend(
            [
                "",
                "## Attribution Boundary",
                "",
                "- Public IPs identify infrastructure, not a guaranteed person.",
                "- Use timestamps, process names, ports, and preserved evidence when reporting.",
                "- Report abuse to the ISP/cloud/provider or local network owner; do not retaliate.",
                "",
                "## Defensive Next Steps",
                "",
                "- Review findings before enabling auto-containment.",
                "- Rotate credentials from a clean device after confirmed compromise.",
                "- Preserve runtime/evidence and reports before reinstalling software.",
                "- Report malicious infrastructure to its provider or CERT.",
            ]
        )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def _events(self) -> list[dict[str, Any]]:
        if not self.config.event_log.exists():
            return []
        events = []
        for line in self.config.event_log.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
