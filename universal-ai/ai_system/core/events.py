from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ai_system.core.config import load_settings


@dataclass
class Event:
    id: str
    timestamp: str
    kind: str
    message: str


class EventLog:
    def __init__(self, path: Path | None = None) -> None:
        settings = load_settings()
        self.path = path or settings.root / "logs" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, message: str) -> Event:
        event = Event(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            kind=kind,
            message=message,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        return event

    def tail(self, limit: int = 50) -> list[Event]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        events: list[Event] = []
        for line in lines:
            try:
                events.append(Event(**json.loads(line)))
            except Exception:
                continue
        return events
