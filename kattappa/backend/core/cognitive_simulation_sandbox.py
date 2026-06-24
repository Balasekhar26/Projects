# cognitive_simulation_sandbox.py
# ==============================
# Cognitive Simulation Sandbox (CSS) orchestrator.
# Implements "mental rehearsal" before execution.

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.identity_system import IdentitySystem
from backend.core.simulation_sandbox import SimulationSandbox, SandboxReport, SandboxVerdict
from backend.core.consensus_engine import ConsensusEngine, AgentOutput, Decision, Recommendation, DecisionContext, ConsensusDecision
from backend.core.goal_memory import GoalMemory


@dataclass(frozen=True)
class PredictionItem:
    criterion_type: str
    target: str
    predicted_pass: bool
    confidence: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_type": self.criterion_type,
            "target": self.target,
            "predicted_pass": self.predicted_pass,
            "confidence": round(self.confidence, 4),
            "message": self.message,
        }


@dataclass(frozen=True)
class VerificationPredictionReport:
    predicted_success: bool
    predicted_score: float
    items: list[PredictionItem]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicted_success": self.predicted_success,
            "predicted_score": round(self.predicted_score, 4),
            "items": [i.to_dict() for i in self.items],
            "warnings": self.warnings,
        }


class VerificationPredictionEngine:
    """Predicts outcome of GoalVerificationEngine success criteria check based on plan steps."""

    @classmethod
    def predict(cls, success_criteria: dict[str, Any], plan_steps: list[dict[str, Any]]) -> VerificationPredictionReport:
        items: list[PredictionItem] = []
        warnings: list[str] = []
        
        # Flatten all plan step fields (actions, reasons, paths) to scan them easily
        step_texts = []
        for step in plan_steps:
            action = str(step.get("action") or "").lower()
            desc = str(step.get("description") or step.get("reason") or "").lower()
            step_texts.append(f"{action} {desc}")

        # 1. File checks prediction
        files_to_check = success_criteria.get("file_paths") or []
        for f in files_to_check:
            # We predict if a file check will pass: does any step modify or create this file path?
            f_lower = str(f).lower()
            matched = False
            for text in step_texts:
                if f_lower in text or any(action_term in text for action_term in ("write", "create", "edit", "save", "modify")):
                    if f_lower in text:
                        matched = True
                        break
            
            if matched:
                items.append(PredictionItem(
                    criterion_type="file_exists",
                    target=f,
                    predicted_pass=True,
                    confidence=0.90,
                    message=f"Plan contains steps matching file path: {f}"
                ))
            else:
                items.append(PredictionItem(
                    criterion_type="file_exists",
                    target=f,
                    predicted_pass=False,
                    confidence=0.40,
                    message=f"No steps explicitly modify or create target path: {f}"
                ))
                warnings.append(f"Missing plan steps addressing required file: {f}")

        # 2. Log checks prediction
        logs_to_check = success_criteria.get("log_check_events") or []
        for log in logs_to_check:
            log_lower = str(log).lower()
            matched = any(log_lower in t or "log" in t for t in step_texts)
            if matched:
                items.append(PredictionItem(
                    criterion_type="log_event",
                    target=log,
                    predicted_pass=True,
                    confidence=0.85,
                    message=f"Plan contains steps generating log: {log}"
                ))
            else:
                items.append(PredictionItem(
                    criterion_type="log_event",
                    target=log,
                    predicted_pass=False,
                    confidence=0.50,
                    message=f"No steps explicitly write to log: {log}"
                ))
                warnings.append(f"Missing logging action for: {log}")

        # 3. API checks prediction
        apis_to_check = success_criteria.get("api_responses") or []
        for api in apis_to_check:
            api_lower = str(api).lower()
            matched = any(api_lower in t or any(term in t for term in ("api", "http", "fetch", "request", "call")) for t in step_texts)
            if matched:
                items.append(PredictionItem(
                    criterion_type="api_status",
                    target=api,
                    predicted_pass=True,
                    confidence=0.80,
                    message=f"Plan contains steps contacting API: {api}"
                ))
            else:
                items.append(PredictionItem(
                    criterion_type="api_status",
                    target=api,
                    predicted_pass=False,
                    confidence=0.30,
                    message=f"No steps explicitly contact API endpoint: {api}"
                ))
                warnings.append(f"Missing API action mapping: {api}")

        # Calculate predicted score
        if not items:
            predicted_score = 1.0
            predicted_success = True
        else:
            passing = [i for i in items if i.predicted_pass]
            predicted_score = len(passing) / len(items)
            predicted_success = predicted_score >= 0.70

        return VerificationPredictionReport(
            predicted_success=predicted_success,
            predicted_score=predicted_score,
            items=items,
            warnings=warnings
        )


class CognitiveSimulationSandbox:
    """Orchestrates LIS Weight Resolution -> Sandbox Simulation -> Verification Prediction -> Consensus."""

    @classmethod
    def orchestrate(
        cls,
        plan_steps: list[dict[str, Any]],
        *,
        goal_id: str | None = None,
        project_id: str | None = None,
        goal_title: str = "",
        plan_title: str = "",
        plan_description: str = "",
        success_criteria: list[Any] | None = None,
    ) -> dict[str, Any]:
        return cls.run_pipeline(
            plan_steps=plan_steps,
            goal_id=goal_id,
            project_id=project_id,
            goal_title=goal_title,
            plan_title=plan_title,
            plan_description=plan_description,
        )

    @classmethod
    def run_pipeline(
        cls,
        plan_steps: list[dict[str, Any]],
        *,
        goal_id: str | None = None,
        project_id: str | None = None,
        goal_title: str = "",
        plan_title: str = "",
        plan_description: str = "",
    ) -> dict[str, Any]:
        pipeline_id = f"css_{uuid.uuid4().hex[:8]}"

        # 1. Resolve originating goal to fetch success criteria & absolute policies
        goal = None
        if goal_id:
            goal = GoalMemory.get_goal(goal_id)
        elif project_id:
            try:
                from backend.core.personal_project_manager import PersonalProjectManager
                proj = PersonalProjectManager.get_project(project_id)
                if proj:
                    goal_id = proj.get("linked_goal_id")
                    if goal_id:
                        goal = GoalMemory.get_goal(goal_id)
            except Exception:
                pass

        success_criteria = {}
        if goal:
            raw_criteria = goal.get("success_criteria") or "[]"
            try:
                decoded = json.loads(raw_criteria)
            except Exception:
                decoded = []
            
            if isinstance(decoded, dict):
                success_criteria = decoded
            elif isinstance(decoded, list):
                file_paths = []
                log_check_events = []
                api_responses = []
                for item in decoded:
                    item_str = str(item)
                    if item_str.startswith("file_exists:"):
                        file_paths.append(item_str.split(":", 1)[1].strip())
                    elif item_str.startswith("file_contains:"):
                        parts = item_str.split(":", 1)[1].split("->", 1)
                        file_paths.append(parts[0].strip())
                    elif item_str.startswith("log_event:"):
                        log_check_events.append(item_str.split(":", 1)[1].strip())
                    elif item_str.startswith("api_status:"):
                        api_responses.append(item_str.split(":", 1)[1].strip())
                success_criteria = {
                    "file_paths": file_paths,
                    "log_check_events": log_check_events,
                    "api_responses": api_responses
                }

        # 2. LIS Weight Resolution
        lis_context = {
            "task_type": "execution",
            "domain": plan_title or (goal.get("title") if goal else "")
        }
        dynamic_weights = IdentitySystem.derive_role_weights(lis_context)

        # 3. Sandbox Simulation (Resource Exhaustion + Scenario Paths + Dependency check)
        if project_id:
            sandbox_report = SimulationSandbox.evaluate_project_plan(
                project_id=project_id,
                plan_steps=plan_steps,
                goal_id=goal_id,
                goal=goal_title or (goal.get("title") if goal else ""),
            )
        else:
            sandbox_report = SimulationSandbox.evaluate_plan(
                plan_steps=plan_steps,
                goal=goal_title or (goal.get("title") if goal else ""),
                goal_id=goal_id,
                plan_title=plan_title,
                plan_description=plan_description,
            )

        # 4. Verification Prediction
        vp_report = VerificationPredictionEngine.predict(success_criteria, plan_steps)

        # 5. Compile Agent Outputs for the Consensus Engine
        agent_outputs = cls._compile_consensus_inputs(sandbox_report, vp_report)

        # 6. Consensus Engine Decision
        context = DecisionContext(
            project=project_id or "",
            code_change=any("code" in str(s.get("action", "")).lower() for s in plan_steps),
        )
        consensus_decision = ConsensusEngine.decide(agent_outputs, context)

        # 7. MRAL Reasoning Trace persistence
        from backend.core.meta_cognition import MRALAuditor
        from backend.core.cognitive_dashboard import CognitiveDashboardManager

        profile = IdentitySystem.get_or_create_profile("default_profile")
        alarms = {
            "SYCOPHANCY_INDEX": "CLEAR",
            "RELIABILITY_GAP": "CLEAR",
            "CHATTER_DECAY": "CLEAR",
            "CREATIVITY_ERRORS": "CLEAR"
        }
        db_conn = IdentitySystem._get_sqlite_conn()
        try:
            drift_exists = db_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lis_drift_tracker'").fetchone()
            if drift_exists:
                for akey in alarms.keys():
                    arow = db_conn.execute("SELECT is_alarm_tripped FROM lis_drift_tracker WHERE metric_monitored = ? ORDER BY updated_at DESC LIMIT 1", (akey,)).fetchone()
                    if arow and arow["is_alarm_tripped"] == 1:
                        alarms[akey] = "WARNING"
        except Exception:
            pass
        finally:
            db_conn.close()

        r_weights = {"TEACHER": 25, "ENGINEER": 25, "SCIENTIST": 25, "BUILDER": 25}
        if dynamic_weights:
            for k in r_weights.keys():
                r_weights[k] = int((dynamic_weights.get(k.capitalize()) or dynamic_weights.get(k) or 0.25) * 100.0)

        mral_res = MRALAuditor.record_decision_trace(
            goal_id=goal_id,
            goal_title=goal_title or (goal.get("title") if goal else "Plan Decision"),
            goal_description=plan_description or (goal.get("description") if goal else ""),
            plan_steps=plan_steps,
            consensus_decision=consensus_decision.to_dict(),
            sandbox_report=sandbox_report.to_dict(),
            verification_prediction=vp_report.to_dict(),
            research_topics=CognitiveDashboardManager.RESEARCH_TOPICS,
            lis_profile=profile,
            lis_alarms=alarms,
            role_weights=r_weights
        )

        return {
            "pipeline_id": pipeline_id,
            "dynamic_weights": dynamic_weights,
            "sandbox_report": sandbox_report.to_dict(),
            "verification_prediction": vp_report.to_dict(),
            "consensus_decision": consensus_decision.to_dict(),
            "final_verdict": consensus_decision.status.value,
            "requires_human_approval": consensus_decision.requires_human_approval,
            "mral_audit": mral_res,
        }

    @classmethod
    def _compile_consensus_inputs(
        cls,
        sandbox: SandboxReport,
        vp: VerificationPredictionReport
    ) -> list[AgentOutput]:
        outputs = []

        # Engineer Agent: evaluates structural resource forecast
        eng_decision = Decision.APPROVE
        eng_rationale = "Resources within acceptable limits."
        if sandbox.resource_forecast and sandbox.resource_forecast.any_exhaustion_risk:
            eng_decision = Decision.REJECT
            eng_rationale = sandbox.resource_forecast.exhaustion_warning

        outputs.append(AgentOutput(
            agent="Engineer",
            decision=eng_decision,
            confidence=0.90,
            recommendations=(Recommendation("Engineer", eng_rationale),),
            rationale=eng_rationale
        ))

        # Scientist Agent: evaluates verification predictions
        sci_decision = Decision.APPROVE
        sci_rationale = f"Verification prediction matches success criteria (score {vp.predicted_score})."
        if not vp.predicted_success:
            sci_decision = Decision.REJECT
            sci_rationale = f"Verification criteria predicted to fail: {', '.join(vp.warnings)}"

        outputs.append(AgentOutput(
            agent="Scientist",
            decision=sci_decision,
            confidence=0.85,
            recommendations=(Recommendation("Scientist", sci_rationale),),
            rationale=sci_rationale
        ))

        # Builder Agent: evaluates execution scenario paths
        bld_decision = Decision.APPROVE
        bld_rationale = "Optimistic and nominal scenario paths demonstrate proceed readiness."
        if sandbox.verdict == SandboxVerdict.BLOCKED:
            bld_decision = Decision.REJECT
            bld_rationale = f"Sandbox blocked proceed recommendation: {sandbox.reason}"
        elif sandbox.verdict == SandboxVerdict.RECOMMEND_REVISE:
            bld_decision = Decision.ABSTAIN
            bld_rationale = f"Sandbox recommends revision before proceed: {sandbox.reason}"

        outputs.append(AgentOutput(
            agent="Builder",
            decision=bld_decision,
            confidence=0.80,
            recommendations=(Recommendation("Builder", bld_rationale),),
            rationale=bld_rationale
        ))

        # Teacher Agent: evaluates value and context comprehension
        tch_decision = Decision.APPROVE
        tch_rationale = f"Comprehension alignment score: {sandbox.alignment_gate.value_alignment_score}"
        if sandbox.alignment_gate.goal_alignment_score < 0.50:
            tch_decision = Decision.ABSTAIN
            tch_rationale = f"Goal alignment low: {sandbox.alignment_gate.reason}"

        outputs.append(AgentOutput(
            agent="Teacher",
            decision=tch_decision,
            confidence=0.80,
            recommendations=(Recommendation("Teacher", tch_rationale),),
            rationale=tch_rationale
        ))

        return outputs


def json_loads_safe(val: str) -> Any:
    try:
        return json.loads(val)
    except Exception:
        # Return lists if it looks like a list
        if val.strip().startswith("[") and val.strip().endswith("]"):
            clean = val.strip()[1:-1].split(",")
            return [c.strip().strip('"').strip("'") for c in clean if c.strip()]
        return []
