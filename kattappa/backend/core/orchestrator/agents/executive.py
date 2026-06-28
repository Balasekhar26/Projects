"""ExecutiveAgent — Phase K9 upgrade.

Now calls DecisionClassifier before delegating any task.  For ETHICAL,
PLANNING, CONFLICT, PERSONAL, and UNCERTAIN question types the WisdomEngine
is invoked and its guidance is injected into SharedContext so the Planner
and downstream agents can consult it.
"""
from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event


class ExecutiveAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Executive"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("executive_agent_exec", "Executive Agent executing task")
        message = task.params.get("message") or context.get("user_input") or ""

        # ── K9: Decision Classification ──────────────────────────────────────
        try:
            from backend.core.wisdom.classifier import DecisionClassifier
            from backend.core.wisdom.wisdom_engine import WisdomEngine
            from backend.core.wisdom.science_engine import ScienceEngine

            classification = DecisionClassifier.classify(message)
            context.set("question_type", classification.primary)
            context.set("question_labels", [
                {"label": lw.label, "weight": round(lw.weight, 3)}
                for lw in classification.labels
            ])
            context.set("decision_classifier_confidence",
                        classification.labels[0].weight if classification.labels else 0.0)

            if classification.use_wisdom_engine:
                advice = WisdomEngine.advise(
                    question=message,
                    domains=classification.suggested_domains,
                    context=context.to_dict(),
                )
                context.set("wisdom_guidance", advice.summary)
                context.set("wisdom_principles", [p.id for p in advice.principles])
                log_event(
                    "executive_wisdom_applied",
                    f"WisdomEngine: {len(advice.principles)} principles | labels={[lw.label for lw in classification.labels]}",
                )
            if classification.use_science_engine:
                sci = ScienceEngine.advise(message)
                context.set("recommended_agent", sci.recommended_agent)
                log_event(
                    "executive_science_routed",
                    f"ScienceEngine: route to {sci.recommended_agent!r}",
                )
        except Exception as e:
            log_event("executive_classifier_error", str(e))

        # ── Delegation ────────────────────────────────────────────────────────
        context.set("executive_decision", f"Delegated message: {message}")
        return TaskResult(success=True, output={"decision": "delegated"})

    def terminate(self, task_id: str) -> None:
        pass

