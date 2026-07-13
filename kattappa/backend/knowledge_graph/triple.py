from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Triple:
    """Represents a structured semantic relation inside Kattappa's world model."""
    subject: str
    predicate: str
    object: str
    confidence: float
    timestamp: float
    source: str

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "source": self.source
        }
