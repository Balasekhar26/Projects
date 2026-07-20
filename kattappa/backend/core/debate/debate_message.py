from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class DebateMessage:
    sender: str
    message_type: str  # PROPOSAL, CRITIQUE, REVISION
    content: str
    confidence_score: float = 1.0
    suggestions: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
