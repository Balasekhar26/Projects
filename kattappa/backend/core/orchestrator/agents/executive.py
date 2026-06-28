"""ExecutiveAgent — Phase K20 upgrade (Cognitive CEO).

Coordinates Strategy Selection, Conflict Resolution, Workspace Registers,
Context Manager compilation, Emotion adjustments, Self-Model boundary checking,
and task routing pathways.
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
        log_event("executive_ceo_exec", "Cognitive CEO (Executive Agent) executing task")
        message = task.params.get("message") or context.get("user_input") or ""
        session_id = context.get("chat_session_id") or "kattappa-ceo-session"

        # ── 1. Compile Execution Context ─────────────────────────────────────
        try:
            from backend.core.context_manager import ContextManager
            ctx_data = ContextManager.build_execution_context(session_id, message)
            context.set("compiled_context", ctx_data["compiled_context"])
        except Exception as e:
            log_event("executive_context_builder_error", str(e))

        # ── 2. Self Model Capability & Boundary Evaluation ──────────────────
        try:
            from backend.core.self_model import SelfModel
            allowed, self_score, boundary_reason = SelfModel.evaluate_capability(message)
            context.set("self_confidence_score", self_score)
            if not allowed:
                log_event("executive_boundary_limit_triggered", f"Boundary limit triggered: {boundary_reason}")
                return TaskResult(
                    success=False,
                    output={"decision": "HALT", "reason": boundary_reason},
                    error=f"SelfModel: {boundary_reason}"
                )
        except Exception as e:
            log_event("executive_self_model_error", str(e))

        # ── 3. Emotion Layer Adjustments ─────────────────────────────────────
        try:
            from backend.core.emotion_layer import EmotionLayer
            em_adjustments = EmotionLayer.get_style_adjustments()
            context.set("style_adjustments", em_adjustments)
            log_event("executive_emotion_applied", f"Emotion adjustments loaded: {list(em_adjustments.keys())}")
        except Exception as e:
            log_event("executive_emotion_error", str(e))

        # ── 4. Decision Classification & Wisdom Engine ────────────────────────
        wisdom_guidance = None
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
                wisdom_guidance = {
                    "summary": advice.summary,
                    "block_action": "do not" in advice.summary.lower() or "avoid" in advice.summary.lower(),
                    "reason": advice.summary
                }
                context.set("wisdom_guidance", advice.summary)
                context.set("wisdom_principles", [p.id for p in advice.principles])
                log_event(
                    "executive_wisdom_applied",
                    f"WisdomEngine advice set: {advice.summary[:60]}...",
                )
            if classification.use_science_engine:
                sci = ScienceEngine.advise(message)
                context.set("recommended_agent", sci.recommended_agent)
                log_event("executive_science_routed", f"ScienceEngine: route to {sci.recommended_agent!r}")
        except Exception as e:
            log_event("executive_classifier_error", str(e))

        # ── 5. Conflict Resolution ──────────────────────────────────────────
        try:
            from backend.core.conflict_resolver import ConflictResolver
            
            # Formulate hypothetical planner and scientist inputs for arbitration
            planner_advice = {"action": "PROCEED", "confidence": 0.8, "details": "Planner baseline path"}
            world_model_risk = {"risk_score": 0.1, "risk_description": "Low risk"}
            # Let's adjust risk if the prompt contains dangerous terms
            if "delete" in message.lower() or "remove" in message.lower():
                world_model_risk = {"risk_score": 0.6, "risk_description": "File deletion carries moderate risk"}
            
            scientist_evidence = {"p_survival": 0.96, "details": "Hypothesis validated"}
            if "always" in message.lower() or "never" in message.lower():
                scientist_evidence = {"p_survival": 0.48, "details": "Absolute statements penalized"}

            decision = ConflictResolver.resolve(
                planner_advice=planner_advice,
                world_model_risk=world_model_risk,
                scientist_evidence=scientist_evidence,
                wisdom_guidance=wisdom_guidance
            )
            
            context.set("resolution_decision", decision.action)
            context.set("resolution_explanation", decision.explanation)
            
            if decision.action == "HALT":
                log_event("executive_ceo_halted", f"CEO halted execution: {decision.explanation}")
                return TaskResult(
                    success=False,
                    output={"decision": "HALT", "explanation": decision.explanation},
                    error=f"ConflictResolver: {decision.explanation}"
                )
            elif decision.action == "USER_APPROVAL_REQUIRED":
                log_event("executive_ceo_throttled", "CEO waiting for user approval")
                return TaskResult(
                    success=True,
                    output={"decision": "USER_APPROVAL_REQUIRED", "explanation": decision.explanation}
                )
        except Exception as e:
            log_event("executive_conflict_resolution_error", str(e))

        # ── 6. Active Executive Workspace Staging ───────────────────────────
        try:
            from backend.core.executive_workspace import WORKSPACE
            WORKSPACE.reset_workspace()
            WORKSPACE.write_scratchpad("current_query", message)
            WORKSPACE.set_register("session_id", session_id)
            WORKSPACE.enqueue_thought("Executive CEO completed initial routing triage")
        except Exception as e:
            log_event("executive_workspace_error", str(e))

        # ── 7. Delegation ───────────────────────────────────────────────────
        context.set("executive_decision", f"Delegated message: {message}")
        return TaskResult(
            success=True,
            output={
                "decision": "PROCEED",
                "recommended_agent": context.get("recommended_agent") or "Planner"
            }
        )

    def terminate(self, task_id: str) -> None:
        pass

