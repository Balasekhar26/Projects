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
    trust_tag: str = "SYSTEM_TRUST"


def classify_risk(text: str, trust_tag: str = "SYSTEM_TRUST") -> RiskDecision:
    lower = text.lower()
    blocked_hit = next((word for word in BLOCKED_KEYWORDS if word in lower), None)
    if blocked_hit:
        return RiskDecision("blocked", False, True, f"Blocked keyword: {blocked_hit}", trust_tag)

    risky_hit = next((word for word in RISKY_KEYWORDS if word in lower), None)
    if risky_hit:
        if trust_tag == "UNTRUSTED_ENVIRONMENT":
            return RiskDecision("blocked", False, True, f"Blocked untrusted action: {risky_hit}", trust_tag)
        return RiskDecision("medium", True, False, f"Approval keyword: {risky_hit}", trust_tag)

    return RiskDecision("safe", False, False, "No risky action detected", trust_tag)
