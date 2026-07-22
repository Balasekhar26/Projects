from __future__ import annotations
import os
import json
from typing import Any
from backend.agents.planner import TaskGraph, TaskStep
from backend.core.planner.intent_classifier import IntentClassifier
from backend.core.planner.constraint_extractor import ConstraintExtractor
from backend.core.planner.context_builder import ContextBuilder
from backend.core.planner.risk_engine import RiskEngine
from backend.core.planner.verification_engine import VerificationEngine
from backend.core.planner.dag_builder import DAGBuilder
from backend.core.model_router import ask_model

class PlannerEngine:
    @classmethod
    def decompose(cls, goal: str, context: dict[str, Any] | None = None) -> TaskGraph:
        """Decomposes a user goal into a topologically sorted TaskGraph using K17/K18 context and constraints."""
        from backend.core.skills.skill_selector import SkillSelector
        from backend.core.skills.skill_executor import SkillExecutor
        
        matched_skill = SkillSelector.select_skill(goal, context)
        if matched_skill:
            return SkillExecutor.execute_skill(matched_skill, goal)
            
        intent = IntentClassifier.classify_intent(goal)
        constraints = ConstraintExtractor.extract_constraints(goal)
        aggregated_context = ContextBuilder.build_context(goal)
        
        import sys
        use_mock = (
            (os.getenv("KATTAPPA_ENV") == "test" or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true")
            and os.getenv("KATTAPPA_FORCE_REAL_PLANNING") != "true"
        )

        raw_steps = []

        if use_mock:
            lower_goal = goal.lower()
            if "write" in lower_goal and "test" in lower_goal:
                raw_steps = [
                    {
                        "step_id": "step1",
                        "description": "Write the implementation file",
                        "agent": "coder",
                        "action": "WRITE_FILE",
                        "params": {"target": "backend/core/sample.py", "content": "print('hello')"},
                        "dependencies": []
                    },
                    {
                        "step_id": "step2",
                        "description": "Run the verification tests",
                        "agent": "coder",
                        "action": "RUN_TESTS",
                        "params": {"target": "backend/tests/test_sample.py"},
                        "dependencies": ["step1"]
                    }
                ]
            elif "read" in lower_goal and "search" in lower_goal:
                raw_steps = [
                    {
                        "step_id": "read_step",
                        "description": "Read configuration details",
                        "agent": "file",
                        "action": "READ_FILE",
                        "params": {"target": "backend/config.yaml"},
                        "dependencies": []
                    },
                    {
                        "step_id": "search_step",
                        "description": "Search web for updates",
                        "agent": "researcher",
                        "action": "BROWSER_SEARCH",
                        "params": {"query": "latest kattappa OS config"},
                        "dependencies": []
                    }
                ]
            else:
                # Default mock planner steps
                raw_steps = [
                    {
                        "step_id": "step1",
                        "description": f"Perform initial {intent} step",
                        "agent": "coder" if intent == "coding" else "researcher",
                        "action": "RUN_SHELL" if intent == "coding" else "BROWSER_SEARCH",
                        "params": {"command": "echo hello"} if intent == "coding" else {"query": goal},
                        "dependencies": []
                    }
                ]
        else:
            prompt = (
                f"You are a Cognitive Task Planner.\n"
                f"Decompose the following user goal into planning steps.\n"
                f"Goal: {goal}\n"
                f"Intent Category: {intent}\n"
                f"Constraints: {json.dumps(constraints)}\n"
                f"System Environment & Memory: {json.dumps(aggregated_context)}\n\n"
                f"Output ONLY a valid JSON array of objects. Each object must contain:\n"
                f"- step_id (string, unique)\n"
                f"- description (string)\n"
                f"- agent (string, e.g. 'coder', 'researcher', 'file', 'browser')\n"
                f"- action (string, e.g. 'WRITE_FILE', 'RUN_SHELL', 'BROWSER_SEARCH')\n"
                f"- params (dict)\n"
                f"- dependencies (list of strings, step_ids this step depends on)\n"
                f"Example: "
                f'[{{"step_id": "s1", "description": "init venv", "agent": "coder", "action": "RUN_SHELL", "params": {{"command": "python -m venv venv"}}, "dependencies": []}}]'
            )
            try:
                import backend.core.model_router as model_router
                res = model_router.ask_model(prompt, role="planning")
                if res is not None:
                    clean_res = res.strip()
                    if clean_res.startswith("```json"):
                        clean_res = clean_res[7:]
                    if clean_res.endswith("```"):
                        clean_res = clean_res[:-3]
                    clean_res = clean_res.strip()
                    parsed = json.loads(clean_res)
                    if isinstance(parsed, list):
                        raw_steps = parsed
            except Exception:
                raw_steps = []

        if not isinstance(raw_steps, list):
            raw_steps = []
                
        # Enrich generated steps with Risk, Verification, and Approval values
        enriched_steps = []
        for step in raw_steps:
            action = step["action"]
            params = step.get("params") or {}
            
            risk = RiskEngine.estimate_risk(action, params)
            verify_method = VerificationEngine.get_verification_method(action, params)
            
            step["risk_level"] = risk
            step["approval_required"] = (risk == "HIGH" or constraints.get("local_only") is True)
            step["failure_recovery"] = verify_method
            enriched_steps.append(step)
            
        # Topologically sort and validate the dependency DAG
        ordered_steps = DAGBuilder.validate_and_order(enriched_steps)
        
        # Build and populate final TaskGraph
        graph = TaskGraph(goal)
        for s in ordered_steps:
            task_step = TaskStep(
                step_id=s["step_id"],
                description=s["description"],
                agent=s["agent"],
                action=s["action"],
                params=s["params"],
                dependencies=s["dependencies"],
                risk_level=s["risk_level"],
                approval_required=s["approval_required"],
                failure_recovery=s["failure_recovery"]
            )
            graph.add_step(task_step)
            
        from backend.core.debate.debate_engine import DebateEngine
        debated_graph, confidence, decision = DebateEngine.run_debate(graph)
        
        # Apply calibration using K23 EvaluationEngine
        from backend.core.evaluation.evaluation_engine import EvaluationEngine
        calibrated_confidence = EvaluationEngine.calibrate_confidence(confidence)
        
        setattr(debated_graph, "debate_confidence", calibrated_confidence)
        setattr(debated_graph, "debate_decision", decision)
        
        # Ensure task_id exists and record prediction metrics
        task_id = getattr(debated_graph, "task_id", None)
        if not task_id:
            import uuid
            task_id = str(uuid.uuid4())
            setattr(debated_graph, "task_id", task_id)
            
        EvaluationEngine.record_prediction(
            task_id=task_id,
            predicted_confidence=confidence,
            predicted_duration=30.0,
            predicted_memory_usage=1.5,
            predicted_success_probability=confidence
        )
        
        return debated_graph
