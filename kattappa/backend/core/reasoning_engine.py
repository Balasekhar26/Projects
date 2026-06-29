"""Reasoning Engine — Kattappa OS v2 Reasoning Kernel.

Upgraded from a 108-line heuristic analyzer to a full Reasoning Kernel that:

1. Opens a Blackboard workspace per reasoning session (structured chain-of-thought)
2. Runs structured reasoning: Intent → Domain → Assumptions → Evidence →
   Missing Information → Capability Gaps → Risks → Verdict
3. Writes each step as a BlackboardEntry with provenance
4. Consults CapabilityGraph for capability gap detection
5. Consults WorldModel for entity context (project, resources, risks)
6. Emits EventBus events (BeliefUpdated, CapabilityAssessed, CognitiveStateChanged)
7. Returns a structured ReasoningTrace (serializable, storable in ledger)

Backward compatible: the original analyze() method signature is preserved.
The new reason() method provides the full Kernel behavior.
"""

from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from typing import Any

from backend.core.event_bus import EventBus, EventName
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# ReasoningTrace — structured output of a full reasoning session
# ---------------------------------------------------------------------------

@dataclass
class ReasoningTrace:
    """Serializable output of one ReasoningEngine.reason() invocation."""
    trace_id: str = ""
    goal_title: str = ""
    goal_description: str = ""
    session_id: str = "primary"
    domain: str = "General"
    intent: str = ""
    status: str = "READY_TO_PLAN"           # READY_TO_PLAN | REQUIRES_CLARIFICATION | BLOCKED_ON_CAPABILITY
    assumptions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    capability_gaps: list[dict[str, str]] = field(default_factory=list)
    risks: list[dict[str, str]] = field(default_factory=list)
    memory_context: str = ""
    world_context: dict[str, Any] = field(default_factory=dict)
    blackboard_entries: list[dict[str, Any]] = field(default_factory=list)
    analyzed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "goal_title": self.goal_title,
            "domain": self.domain,
            "intent": self.intent,
            "status": self.status,
            "assumptions": self.assumptions,
            "evidence": self.evidence,
            "missing_information": self.missing_information,
            "clarification_questions": self.clarification_questions,
            "capability_gaps": self.capability_gaps,
            "risks": self.risks,
            "memory_context": self.memory_context,
            "world_context": self.world_context,
            "blackboard_entries": self.blackboard_entries,
            "analyzed_at": self.analyzed_at,
        }


# ---------------------------------------------------------------------------
# Domain classifier (shared between analyze() and reason())
# ---------------------------------------------------------------------------

def _classify_domain(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["rust", "python", "compile", "code", "file", "module", "import", "class", "function"]):
        return "Software Development"
    if any(w in t for w in ["deploy", "server", "cloud", "docker", "kubernetes", "ci/cd", "pipeline", "port", "host"]):
        return "DevOps/Infrastructure"
    if any(w in t for w in ["drone", "fly", "hardware", "iot", "sensor", "firmware", "embedded"]):
        return "Hardware/IoT"
    if any(w in t for w in ["memory", "recall", "cognitive", "belief", "planner", "agent", "blackboard"]):
        return "AI/Cognitive Systems"
    if any(w in t for w in ["finance", "trade", "market", "stock", "investment", "budget"]):
        return "Finance"
    return "General"


def _extract_assumptions(domain: str, text: str) -> list[str]:
    assumptions = []
    t = text.lower()
    if domain == "Software Development":
        assumptions.append("Implicit dependency: compiler or interpreter is installed locally.")
        if "test" in t:
            assumptions.append("Test runner (pytest/jest) is installed and configured.")
        assumptions.append("Target file paths are relative to the active workspace folder.")
    elif domain == "DevOps/Infrastructure":
        assumptions.append("Target cloud egress endpoints are whitelisted in firewall rules.")
        assumptions.append("Proper configuration files (.env, docker-compose) are present.")
    elif domain == "Hardware/IoT":
        assumptions.append("Physical limitation: route distances must respect battery and wind speeds.")
        assumptions.append("Firmware flashing requires physical access or OTA-enabled device.")
    elif domain == "AI/Cognitive Systems":
        assumptions.append("LLM model is loaded and responsive via Ollama router.")
        assumptions.append("Memory subsystems are initialized and schema migrations are current.")
    elif domain == "Finance":
        assumptions.append("Market data feeds are available and latency is within acceptable bounds.")
    else:
        assumptions.append("Assumes environment context is clean and permissions are pre-authorized.")
    return assumptions


def _detect_missing_info(domain: str, text: str) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    questions: list[str] = []
    t = text.lower()

    if domain == "Software Development":
        if not any(w in t for w in ["rust", "python", "javascript", "typescript", "c++", "go", "java", "kotlin"]):
            missing.append("Programming language choice is unspecified.")
            questions.append("Which programming language or runtime environment should be used?")
        has_path = "file" in t or "path" in t or any(ext in t for ext in [".py", ".rs", ".js", ".ts", ".cpp", ".go", ".java", ".json"])
        if not has_path:
            missing.append("Target path or output filename is unspecified.")
            questions.append("What is the target filename or output path?")

    if domain == "DevOps/Infrastructure":
        if "port" not in t and "host" not in t and "url" not in t and "endpoint" not in t:
            missing.append("Target server host, port, or environment URL is missing.")
            questions.append("What is the destination host IP, target port, or environment URL?")

    if domain == "Hardware/IoT":
        if "battery" not in t and "range" not in t and "mah" not in t:
            missing.append("Battery capacity or range constraints not specified.")
            questions.append("What are the battery capacity and expected flight/operating range?")

    return missing, questions


def _detect_risks(text: str) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    t = text.lower()
    if any(w in t for w in ["delete", "remove", "clean", "drop", "truncate", "purge"]):
        risks.append({
            "category": "REVERSIBILITY_RISK",
            "severity": "high",
            "message": "Destructive operations detected. Rollback checkpoints must be created before execution.",
        })
    if any(w in t for w in ["sudo", "root", "admin", "superuser"]):
        risks.append({
            "category": "PRIVILEGE_RISK",
            "severity": "critical",
            "message": "Elevated privileges requested. Violates minimum-security privilege bounds.",
        })
    if any(w in t for w in ["secret", "password", "token", "api_key", "credential"]):
        risks.append({
            "category": "CREDENTIAL_RISK",
            "severity": "high",
            "message": "Credential or secret reference detected. Secrets must be loaded from env, never hardcoded.",
        })
    if any(w in t for w in ["production", "prod ", "live system", "customer data"]):
        risks.append({
            "category": "PRODUCTION_RISK",
            "severity": "high",
            "message": "Production environment targeted. HIGH_ASSURANCE cognitive mode required.",
        })
    return risks


# ---------------------------------------------------------------------------
# ReasoningEngine
# ---------------------------------------------------------------------------

class ReasoningEngine:
    """Reasoning Engine — Phase 3 Reasoning Kernel.

    Two entry points:
    - analyze(): original heuristic analysis (fast, no Blackboard, backward compatible)
    - reason(): full Kernel run with Blackboard, CapabilityGraph, WorldModel, EventBus
    """

    # -- original interface (backward compatible) ---------------------------

    @classmethod
    def analyze(
        cls,
        goal_title: str,
        goal_description: str,
        session_id: str = "primary",
    ) -> dict[str, Any]:
        """Fast heuristic analysis. Preserved for backward compatibility."""
        now = time.time()
        text = f"{goal_title} {goal_description}"
        domain = _classify_domain(text)

        context_data: dict[str, Any] = {}
        try:
            from backend.core.memory_broker import MemoryBroker
            context_data = MemoryBroker.retrieve(query=goal_title, session_id=session_id)
        except Exception as e:
            log_event(f"ReasoningEngine analyze: memory retrieval failed: {e}")

        assumptions = _extract_assumptions(domain, text)
        missing_info, clarification_questions = _detect_missing_info(domain, text)
        risks = _detect_risks(text)

        status = "REQUIRES_CLARIFICATION" if clarification_questions else "READY_TO_PLAN"

        return {
            "status": status,
            "domain": domain,
            "assumptions": assumptions,
            "missing_information": missing_info,
            "clarification_questions": clarification_questions,
            "risks": risks,
            "memory_context": context_data.get("unified_context_string", "No matching historical memory found."),
            "analyzed_at": now,
        }

    # -- full Reasoning Kernel ---------------------------------------------

    @classmethod
    def reason(
        cls,
        goal_title: str,
        goal_description: str,
        session_id: str = "primary",
        required_capabilities: list[str] | None = None,
    ) -> ReasoningTrace:
        """Full reasoning kernel with Blackboard, CapabilityGraph, WorldModel.

        Steps:
        1. Open Blackboard workspace
        2. Classify domain & intent
        3. Extract assumptions → write to Blackboard
        4. Retrieve memory evidence → write to Blackboard
        5. Detect missing information → write to Blackboard
        6. Check capability gaps → emit CapabilityAssessed event
        7. Assess risks → write to Blackboard
        8. Query WorldModel for entity context
        9. Determine verdict (READY_TO_PLAN | REQUIRES_CLARIFICATION | BLOCKED_ON_CAPABILITY)
        10. Destroy Blackboard; return ReasoningTrace
        """
        import uuid as _uuid
        trace_id = _uuid.uuid4().hex[:16]
        now = time.time()
        text = f"{goal_title} {goal_description}"
        domain = _classify_domain(text)
        intent = cls._extract_intent(goal_title)

        # -- Step 1: Open Blackboard workspace --------------------------------
        blackboard_entries: list[dict[str, Any]] = []

        def bb_write(kind: str, source: str, content: Any) -> None:
            blackboard_entries.append({
                "kind": kind,
                "source": source,
                "content": content,
                "at": time.time(),
            })

        bb_write("fact", "ReasoningEngine", f"Goal: {goal_title} | Domain: {domain}")

        # -- Step 2: Assumptions ---------------------------------------------
        assumptions = _extract_assumptions(domain, text)
        for a in assumptions:
            bb_write("assumption", "ReasoningEngine", a)

        # -- Step 3: Memory evidence -----------------------------------------
        memory_context_str = "No matching historical memory found."
        evidence: list[str] = []
        try:
            from backend.core.memory_broker import MemoryBroker
            ctx = MemoryBroker.retrieve(query=goal_title, session_id=session_id)
            memory_context_str = ctx.get("unified_context_string", memory_context_str)
            if memory_context_str and memory_context_str != "No matching historical memory found.":
                evidence.append(f"Memory recall: {memory_context_str[:200]}")
                bb_write("fact", "MemoryBroker", evidence[-1])
        except Exception as e:
            log_event(f"ReasoningEngine.reason: memory retrieval failed: {e}")
            bb_write("fact", "MemoryBroker", f"Memory unavailable: {e}")

        # -- Step 4: Missing information detection ---------------------------
        missing_info, clarification_questions = _detect_missing_info(domain, text)
        for m in missing_info:
            bb_write("constraint", "ReasoningEngine", f"MISSING: {m}")

        # -- Step 5: Capability gap detection --------------------------------
        capability_gaps: list[dict[str, str]] = []
        required = required_capabilities or cls._infer_capabilities(domain, text)
        try:
            from backend.core.capability_graph import CapabilityGraph
            assessment = CapabilityGraph.assess(goal_title, required)
            gaps = assessment.get("missing", [])
            for gap in gaps:
                cap_name = gap if isinstance(gap, str) else gap.get("name", str(gap))
                capability_gaps.append({
                    "capability": cap_name,
                    "status": "missing",
                    "recommendation": f"Register '{cap_name}' in CapabilityGraph before planning.",
                })
                bb_write("constraint", "CapabilityGraph", f"CAPABILITY_GAP: {cap_name}")
            EventBus.publish(
                EventName.CAPABILITY_ASSESSED,
                {
                    "goal_title": goal_title,
                    "required": required,
                    "gaps": [g["capability"] for g in capability_gaps],
                    "domain": domain,
                },
                source="ReasoningEngine",
            )
        except Exception as e:
            log_event(f"ReasoningEngine.reason: capability check failed: {e}")
            bb_write("fact", "CapabilityGraph", f"Capability check unavailable: {e}")

        # -- Step 6: Risk assessment ----------------------------------------
        risks = _detect_risks(text)
        for r in risks:
            bb_write("constraint", "ReasoningEngine",
                     f"RISK[{r['severity'].upper()}]: {r['category']} — {r['message']}")

        # -- Step 7: WorldModel context --------------------------------------
        world_context: dict[str, Any] = {}
        try:
            from backend.core.world_model import WorldModel
            wm_results = WorldModel.query_world_context(query_text=goal_title)
            world_context = {"entities": wm_results} if wm_results else {}
            if world_context:
                bb_write("fact", "WorldModel", f"World context: {[e.get('name') for e in wm_results[:3]]}")
        except Exception as e:
            log_event(f"ReasoningEngine.reason: world model query failed: {e}")

        # -- Step 8: Verdict -------------------------------------------------
        if capability_gaps:
            status = "BLOCKED_ON_CAPABILITY"
        elif clarification_questions:
            status = "REQUIRES_CLARIFICATION"
        else:
            status = "READY_TO_PLAN"

        bb_write("agent_output", "ReasoningEngine", f"VERDICT: {status}")

        # -- Step 9: Emit belief if risks found ------------------------------
        if risks:
            try:
                from backend.core.human_memory import HumanMemory
                severity = max(risks, key=lambda r: {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(r["severity"], 0))
                HumanMemory.upsert_belief(
                    key=f"goal_risk_{goal_title[:40].lower().replace(' ', '_')}",
                    value=f"{severity['category']}: {severity['message'][:100]}",
                    confidence=0.9,
                )
                EventBus.publish(
                    EventName.BELIEF_UPDATED,
                    {"key": f"goal_risk_{goal_title[:40]}", "status": status},
                    source="ReasoningEngine",
                )
            except Exception as e:
                log_event(f"ReasoningEngine.reason: belief update failed: {e}")

        return ReasoningTrace(
            trace_id=trace_id,
            goal_title=goal_title,
            goal_description=goal_description,
            session_id=session_id,
            domain=domain,
            intent=intent,
            status=status,
            assumptions=assumptions,
            evidence=evidence,
            missing_information=missing_info,
            clarification_questions=clarification_questions,
            capability_gaps=capability_gaps,
            risks=risks,
            memory_context=memory_context_str,
            world_context=world_context,
            blackboard_entries=blackboard_entries,
            analyzed_at=now,
        )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _extract_intent(goal_title: str) -> str:
        t = goal_title.lower().strip()
        if t.startswith("build") or t.startswith("create") or t.startswith("implement"):
            return "BUILD"
        if t.startswith("deploy") or t.startswith("release") or t.startswith("publish"):
            return "DEPLOY"
        if t.startswith("fix") or t.startswith("repair") or t.startswith("debug"):
            return "FIX"
        if t.startswith("analyze") or t.startswith("review") or t.startswith("audit"):
            return "ANALYZE"
        if t.startswith("refactor") or t.startswith("improve") or t.startswith("upgrade"):
            return "REFACTOR"
        if t.startswith("test") or t.startswith("verify") or t.startswith("validate"):
            return "VERIFY"
        return "GENERAL"

    @staticmethod
    def _infer_capabilities(domain: str, text: str) -> list[str]:
        """Infer the set of capabilities likely required based on domain/text."""
        caps: list[str] = []
        t = text.lower()
        if domain == "Software Development":
            caps.append("code_execution")
            if "test" in t:
                caps.append("test_runner")
            if "git" in t or "commit" in t or "push" in t:
                caps.append("git_operations")
        elif domain == "DevOps/Infrastructure":
            caps.append("shell_execution")
            if "docker" in t:
                caps.append("docker")
            if "deploy" in t:
                caps.append("deployment")
        elif domain == "Hardware/IoT":
            caps.append("hardware_access")
        elif domain == "AI/Cognitive Systems":
            caps.append("llm_inference")
        return caps
