from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresenceEvent:
    zone: str
    confidence: float
    timestamp_ms: int
    activity: str = "presence"
    known_user_present: bool = False


@dataclass(frozen=True)
class CyberEvent:
    kind: str
    timestamp_ms: int
    severity: str = "info"
    details: str = ""


@dataclass(frozen=True)
class PresenceCorrelation:
    risk_level: str
    score: int
    reason: str
    recommended_action: str


def correlate_presence(presence: PresenceEvent, cyber_events: list[CyberEvent]) -> PresenceCorrelation:
    nearby = [event for event in cyber_events if abs(event.timestamp_ms - presence.timestamp_ms) <= 120_000]
    suspicious = [event for event in nearby if event.kind in {"login_attempt", "usb_inserted", "privilege_change"}]

    if presence.confidence < 0.55:
        return PresenceCorrelation("low", 10, "Presence confidence is too low to affect cyber risk.", "log_only")

    if presence.known_user_present:
        return PresenceCorrelation("low", 20, "Known user presence reduces physical-risk escalation.", "log_only")

    if suspicious:
        kinds = ", ".join(sorted({event.kind for event in suspicious}))
        return PresenceCorrelation(
            "high",
            85,
            f"Unknown physical presence near device overlaps with cyber event(s): {kinds}.",
            "lock_screen_and_alert",
        )

    return PresenceCorrelation(
        "medium",
        45,
        "Unknown physical presence detected near protected device.",
        "notify_and_monitor",
    )

