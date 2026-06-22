"""Meta-Cognition Engine (Layer 10/11).

Supervises the thinking process itself rather than acting as another agent or planner.
It analyzes uncertainty, conflicts, capability gaps, reasoning traps, and selects
the cognitive mode (DIRECT, DEEP_ANALYSIS, HIGH_ASSURANCE).

As a governor rather than a ruler, it never alters decisions from consensus, validators,
or value engines. It only returns supervision recommendations: ALLOW, ESCALATE,
REQUEST_MORE_EVIDENCE, or CHANGE_REASONING_MODE.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Sequence

from backend.core.capability_graph import CapabilityGraph


class CognitiveMode(str, Enum):
    DIRECT = "DIRECT"
    DEEP_ANALYSIS = "DEEP_ANALYSIS"
    HIGH_ASSURANCE = "HIGH_ASSURANCE"


class SupervisionAction(str, Enum):
    ALLOW = "ALLOW"
    ESCALATE = "ESCALATE"
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"
    CHANGE_REASONING_MODE = "CHANGE_REASONING_MODE"


class MetaCognitionEngine:
    """Monitors and guides Kattappa's cognitive pipeline to enforce safe reasoning."""

    # 1. Select Cognitive Mode
    @classmethod
    def select_cognitive_mode(
        cls, prompt: str, is_production: bool = False, is_code_change: bool = False
    ) -> dict[str, Any]:
        prompt_lower = prompt.lower().strip()
        words = prompt_lower.split()

        # DIRECT mode heuristics (simple calculations or greetings)
        is_simple = (
            (len(words) <= 8
            or prompt_lower in {"hi", "hello", "hey", "status", "ping"}
            or re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", prompt_lower))
            and not any(kw in prompt_lower for kw in {"design", "architect", "feasibility", "equation", "derivation", "physics", "system topology", "dews"})
            and not any(kw in prompt_lower for kw in {"deploy", "production", "prod", "credentials", "auth", "secret"})
        )

        # HIGH_ASSURANCE mode triggers (deployments, code changes, or production environment)
        is_high_assurance = (
            is_production
            or is_code_change
            or any(kw in prompt_lower for kw in {"deploy", "production", "prod", "credentials", "auth", "secret"})
        )

        # DEEP_ANALYSIS mode triggers (complex research, system designs, architecture)
        is_deep_analysis = (
            not is_simple
            and not is_high_assurance
            and (
                len(words) >= 15
                or any(kw in prompt_lower for kw in {"design", "architect", "feasibility", "equation", "derivation", "physics", "system topology", "dews"})
            )
        )

        if is_high_assurance:
            mode = CognitiveMode.HIGH_ASSURANCE
            invoked = ["Validators", "Consensus", "Value Engine", "Policy Engine"]
        elif is_deep_analysis:
            mode = CognitiveMode.DEEP_ANALYSIS
            invoked = ["Router", "Consensus", "Value Engine"]
        else:
            mode = CognitiveMode.DIRECT
            invoked = []

        return {
            "mode": mode.value,
            "invoked_subsystems": invoked,
            "reasons": [
                f"simple={is_simple}",
                f"high_assurance={is_high_assurance}",
                f"deep_analysis={is_deep_analysis}",
            ],
        }

    # 2. Detect Uncertainty
    @classmethod
    def detect_uncertainty(
        cls,
        prompt: str,
        routing_confidence: float,
        evidence_count: int,
        missing_validators: bool,
    ) -> dict[str, Any]:
        reasons = []
        is_low = False

        if routing_confidence < 0.5:
            is_low = True
            reasons.append(f"Low routing confidence: {routing_confidence:.2f}")

        if evidence_count == 0:
            is_low = True
            reasons.append("No supporting tool or simulation evidence registered")

        if missing_validators:
            is_low = True
            reasons.append("Required validators are missing from the routing plan")

        certainty = "LOW" if is_low else "HIGH"
        action = SupervisionAction.REQUEST_MORE_EVIDENCE if is_low else SupervisionAction.ALLOW

        return {
            "certainty": certainty,
            "reasons": reasons,
            "action": action.value,
        }

    # 3. Detect Conflicts
    @classmethod
    def detect_conflicts(
        cls,
        vetoes: Sequence[Any],
        blocking_findings: Sequence[Any],
        consensus_status: str,
        simulation_success_rate: float | None = None,
    ) -> dict[str, Any]:
        reasons = []
        high_conflict = False

        # Vetoes
        failed_vetoes = []
        for v in vetoes:
            # support dict or Veto object
            if isinstance(v, dict):
                if not v.get("passed", True):
                    failed_vetoes.append(v.get("source", "unknown"))
            elif hasattr(v, "passed") and not v.passed:
                failed_vetoes.append(getattr(v, "source", "unknown"))

        if failed_vetoes:
            high_conflict = True
            reasons.append(f"Veto failure detected from: {', '.join(failed_vetoes)}")

        # Blocking findings from Critic
        if blocking_findings:
            high_conflict = True
            reasons.append(f"{len(blocking_findings)} blocking Critic findings identified")

        # Consensus status is escalate or rejected
        if consensus_status in {"escalate", "rejected", "no_feasible_solution"}:
            high_conflict = True
            reasons.append(f"Consensus engine status: {consensus_status}")

        # Simulation failure
        if simulation_success_rate is not None and simulation_success_rate < 0.5:
            high_conflict = True
            reasons.append(f"Simulation success rate too low: {simulation_success_rate:.2%}")

        action = SupervisionAction.ESCALATE if high_conflict else SupervisionAction.ALLOW

        return {
            "high_conflict": high_conflict,
            "conflicts": reasons,
            "action": action.value,
        }

    # 4. Detect Missing Capabilities
    @classmethod
    def detect_missing_capabilities(
        cls, goal: str, required_caps: list[str] | None = None
    ) -> dict[str, Any]:
        if not required_caps:
            return {
                "cannot_execute": False,
                "missing": [],
                "bottlenecks": [],
                "action": SupervisionAction.ALLOW.value,
            }

        assessment = CapabilityGraph.assess(goal, required_caps)
        missing = assessment.get("missing", [])
        bottlenecks = assessment.get("bottlenecks", [])

        cannot_execute = len(missing) > 0
        action = SupervisionAction.ESCALATE if cannot_execute else SupervisionAction.ALLOW

        return {
            "cannot_execute": cannot_execute,
            "missing": missing,
            "bottlenecks": bottlenecks,
            "action": action.value,
        }

    # 5. Detect Reasoning Traps
    @classmethod
    def detect_reasoning_traps(
        cls, chat_history: list[dict[str, Any]] | None, failed_runs_count: int = 0
    ) -> dict[str, Any]:
        traps = []

        # Circular Reasoning (repeated user prompts in recent history)
        if chat_history and len(chat_history) >= 3:
            user_msgs = [m["content"].lower().strip() for m in chat_history if m.get("role") == "user"]
            if len(user_msgs) >= 2 and user_msgs[-1] == user_msgs[-2]:
                traps.append("Circular reasoning trap: prompt repeated consecutively")

        # Repeated failed plans
        if failed_runs_count >= 2:
            traps.append(f"Repeated execution failures: {failed_runs_count} consecutive runs failed")

        action = SupervisionAction.ESCALATE if traps else SupervisionAction.ALLOW

        return {
            "traps_detected": traps,
            "action": action.value,
        }

    # Unified Entry point
    @classmethod
    def supervise(
        cls,
        prompt: str,
        routing_confidence: float = 1.0,
        evidence_count: int = 1,
        missing_validators: bool = False,
        vetoes: Sequence[Any] = (),
        blocking_findings: Sequence[Any] = (),
        consensus_status: str = "approved",
        simulation_success_rate: float | None = None,
        goal: str | None = None,
        required_caps: list[str] | None = None,
        chat_history: list[dict[str, Any]] | None = None,
        failed_runs_count: int = 0,
        is_production: bool = False,
        is_code_change: bool = False,
    ) -> dict[str, Any]:
        """Runs the complete cognitive checks. Returns the recommendation action."""
        mode_res = cls.select_cognitive_mode(prompt, is_production, is_code_change)
        uncertainty_res = cls.detect_uncertainty(prompt, routing_confidence, evidence_count, missing_validators)
        conflict_res = cls.detect_conflicts(vetoes, blocking_findings, consensus_status, simulation_success_rate)
        capability_res = cls.detect_missing_capabilities(goal or prompt, required_caps)
        trap_res = cls.detect_reasoning_traps(chat_history, failed_runs_count)

        # Action precedence: ESCALATE > REQUEST_MORE_EVIDENCE > CHANGE_REASONING_MODE > ALLOW
        final_action = SupervisionAction.ALLOW

        actions = [
            SupervisionAction(uncertainty_res["action"]),
            SupervisionAction(conflict_res["action"]),
            SupervisionAction(capability_res["action"]),
            SupervisionAction(trap_res["action"]),
        ]

        if SupervisionAction.ESCALATE in actions:
            final_action = SupervisionAction.ESCALATE
        elif SupervisionAction.REQUEST_MORE_EVIDENCE in actions:
            final_action = SupervisionAction.REQUEST_MORE_EVIDENCE
        elif mode_res["mode"] == CognitiveMode.DIRECT.value and len(prompt.split()) > 15:
            # Prompt is too long for direct execution, recommend changing mode
            final_action = SupervisionAction.CHANGE_REASONING_MODE

        return {
            "mode": mode_res["mode"],
            "invoked_subsystems": mode_res["invoked_subsystems"],
            "uncertainty": uncertainty_res,
            "conflict": conflict_res,
            "capability": capability_res,
            "trap": trap_res,
            "action": final_action.value,
        }
