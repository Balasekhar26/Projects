from __future__ import annotations

from dataclasses import dataclass


RISKY_KEYWORDS = [
    "delete",
    "format",
    "payment",
    "send email",
    "submit",
    "purchase",
    "transfer money",
    "password",
    "login",
    "install unknown",
    "registry",
    "disable security",
    "rm -rf",
    "del /s",
    "shutdown",
]

BLOCKED_KEYWORDS = [
    "steal",
    "bypass password",
    "malware",
    "keylogger",
    "hide from user",
    "disable logs",
    "exfiltrate",
    "credential dumping",
]


@dataclass(frozen=True)
class RiskDecision:
    level: str
    approval_required: bool
    blocked: bool
    reason: str


def classify_risk(text: str) -> RiskDecision:
    lower = text.lower()
    blocked_hit = next((word for word in BLOCKED_KEYWORDS if word in lower), None)
    if blocked_hit:
        return RiskDecision("blocked", False, True, f"Blocked keyword: {blocked_hit}")

    risky_hit = next((word for word in RISKY_KEYWORDS if word in lower), None)
    if risky_hit:
        return RiskDecision("medium", True, False, f"Approval keyword: {risky_hit}")

    return RiskDecision("safe", False, False, "No risky action detected")
