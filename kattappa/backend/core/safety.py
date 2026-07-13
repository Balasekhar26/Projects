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

    # 3. Secondary dynamic safety classification using GLM-5.2 Governance Reviewer
    from backend.core.model_router import ask_model
    import json
    import re

    prompt = (
        f"You are the Kattappa AI OS Governance Reviewer.\n"
        f"Evaluate the security and risk of the following user request:\n\n"
        f"Request: {text}\n\n"
        f"Rules:\n"
        f"- Analyze if the request attempts dangerous operations, command injection, exfiltration, "
        f"  privilege escalation, system destruction, file deletion, or other malicious actions.\n"
        f"- Return a JSON object with keys:\n"
        f"  * 'risk': one of 'safe', 'medium', 'blocked'\n"
        f"  * 'reason': a brief explanation of the decision\n"
        f"Do not return markdown wrappers, return only the JSON object."
    )
    try:
        response = ask_model(prompt, role="safety")
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            risk_level = data.get("risk", "safe").strip().lower()
            reason = data.get("reason", "Intelligent safety scan complete").strip()
            
            if risk_level == "blocked":
                return RiskDecision("blocked", False, True, f"Intelligent Block: {reason}", trust_tag)
            elif risk_level == "medium":
                return RiskDecision("medium", True, False, f"Intelligent Risk Approval: {reason}", trust_tag)
    except Exception:
        pass

    return RiskDecision("safe", False, False, "No risky action detected", trust_tag)


PROTECTED_FILES = {
    "proposal_engine.py",
    "proposal_governance.py",
    "learning_dashboard.py",
    "burn_in_governance.py",
    "source_trust_engine.py",
    "research_memory.py",
    "safety.py",
    "validators.py",
    "execution_policy.py",
    "approval_workflow.py",
    "approval_continuation.py",
    "reliability_monitor.py",
    "audit"
}


def is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    for filename in PROTECTED_FILES:
        if filename in normalized:
            return True
    return False


