from __future__ import annotations
import uuid
import time
from typing import Any, Dict, List

from backend.core.context_builder import ContextBuilder
from backend.core.intent_classifier import IntentClassifier
from backend.core.goal_generator import GoalGenerator
from backend.core.tool_router import ToolRouter
from backend.core.action_executor import ActionExecutor
from backend.core.observation_engine import ObservationEngine
from backend.core.reflection_engine import ReflectionEngine
from backend.planner.gtpyhop_adapter import GTPyhopAdapter
from backend.planner.task_decomposer import TaskDecomposer, Operator, Method
from backend.planner.belief_store import BeliefStore
from backend.core.memory import remember

class Orchestrator:
    """Coordinates Kattappa's persistent cognitive execution loop components."""

    def __init__(self) -> None:
        self.decomposer = self._setup_decomposer()
        self.belief_store = BeliefStore()

    def _setup_decomposer(self) -> TaskDecomposer:
        decomposer = TaskDecomposer()
        # Declare domains
        decomposer.declare_operator(Operator("check_calendar", {}, {"calendar_checked": True}, estimated_cost=1.0, estimated_time=1.0))
        decomposer.declare_operator(Operator("reserve_slot", {"calendar_checked": True}, {"meeting_booked": True}, estimated_cost=2.0, estimated_time=2.0))
        decomposer.declare_operator(Operator("download_package", {}, {"package_downloaded": True}, estimated_cost=3.0, estimated_time=5.0))
        decomposer.declare_operator(Operator("run_installer", {"package_downloaded": True}, {"software_installed": True}, estimated_cost=4.0, estimated_time=10.0))
        decomposer.declare_operator(Operator("query_version_command", {"software_installed": True}, {"version_verified": True}, estimated_cost=1.0, estimated_time=2.0))
        decomposer.declare_operator(Operator("compile_code", {"has_source": True}, {"code_compiled": True}, estimated_cost=2.0, estimated_time=5.0))
        decomposer.declare_operator(Operator("run_tests", {"code_compiled": True}, {"tests_passed": True}, estimated_cost=1.0, estimated_time=3.0))
        decomposer.declare_operator(Operator("deploy_binary", {"tests_passed": True}, {"app_deployed": True}, estimated_cost=5.0, estimated_time=8.0))

        decomposer.declare_method(Method("do_schedule", "schedule_meeting", {}, ["check_calendar", "reserve_slot"]))
        decomposer.declare_method(Method("do_install", "install_software", {}, ["download_package", "run_installer"]))
        decomposer.declare_method(Method("do_verify", "verify_installation", {"software_installed": True}, ["query_version_command"]))
        decomposer.declare_method(Method("do_compile", "compile_code", {}, ["compile_code"]))
        decomposer.declare_method(Method("do_test", "run_tests", {}, ["run_tests"]))
        decomposer.declare_method(Method("do_deploy", "deploy_binary", {}, ["deploy_binary"]))
        return decomposer

    def run(self, user_input: str) -> Dict[str, Any]:
        logs = []
        logs.append("orchestrator: starting cognitive execution cycle")

        # 1. Build context
        context_data = ContextBuilder.build(user_input)
        logs.append(f"orchestrator: retrieved context -> {context_data['kg_context'][:50]}...")

        # 2. Classify intent
        intent_data = IntentClassifier.classify(user_input)
        logs.append(f"orchestrator: classified intent -> {intent_data['intent']}")

        # 3. Generate goals
        goals = GoalGenerator.generate_goals(intent_data)
        logs.append(f"orchestrator: generated {len(goals)} goals")

        # 4. Invoke Planner
        adapter = GTPyhopAdapter(decomposer=self.decomposer)
        initial_state = {
            "has_source": True,
            "has_ticket": False,
            "calendar_checked": False,
            "package_downloaded": False,
            "software_installed": False,
            "code_compiled": False,
            "tests_passed": False
        }
        
        goal_name = goals[0].name if goals else "compile_code"
        try:
            plan = adapter.create_plan(goal=goal_name, world_state=initial_state, constraints={})
            steps = [step["name"] for step in plan["steps"]]
            logs.append(f"orchestrator: generated HTN plan -> {steps}")
        except Exception as e:
            logs.append(f"orchestrator: planning failed, using fallback: {e}")
            steps = ["compile_code"]

        # 5. Execute Action steps
        executed_steps = []
        final_result = "SUCCESS"
        current_state = dict(initial_state)

        for step in steps:
            agent = ToolRouter.route_step(step)
            logs.append(f"orchestrator: routing step '{step}' to agent '{agent}'")
            
            # Execute step
            exec_res = ActionExecutor.execute(
                agent_name=agent,
                action_type="RUN_SHELL" if agent == "terminal" else "CREATE_FILE",
                params={"command": step},
                state={"chat_session_id": "cognitive-session", "logs": logs, "world_state": current_state}
            )
            
            # Observe step outcomes
            observation = ObservationEngine.observe(step, exec_res)
            logs.append(f"orchestrator: step observation success -> {observation['success']}")

            if not observation["success"]:
                # Trigger plan repair / replanning
                logs.append("orchestrator: step failure detected! Initiating plan repair...")
                try:
                    replan_res = adapter.replan("failed_step", current_state)
                    steps = [s["name"] for s in replan_res["steps"]]
                    logs.append(f"orchestrator: plan repaired successfully, new queue -> {steps}")
                except Exception:
                    logs.append("orchestrator: plan repair failed, aborting execution")
                    final_result = "FAILED"
                    break

            executed_steps.append(step)
            # Update local world state simulation
            if step == "check_calendar":
                current_state["calendar_checked"] = True
            elif step == "reserve_slot":
                current_state["meeting_booked"] = True

        # 6. Update BeliefStore
        self.belief_store.set_belief("last_execution_success", final_result == "SUCCESS", confidence=0.99, source="cognitive_loop")
        logs.append(f"orchestrator: updated BeliefStore -> last_execution_success: {final_result == 'SUCCESS'}")

        # 7. Episodic Memory Consolidation
        try:
            remember(f"Completed orchestration run with result: {final_result}", category="episodic")
        except Exception:
            pass

        # 8. Post-Execution Reflection
        state_repr = {
            "user_input": user_input,
            "execution_plan": executed_steps,
            "result": final_result,
            "logs": logs
        }
        reflections = ReflectionEngine.reflect_on_execution(state_repr)
        logs.append(f"orchestrator: reflection completed -> {reflections['what_succeeded']}")

        return {
            "status": final_result,
            "execution_steps": executed_steps,
            "logs": logs,
            "reflections": reflections,
            "response": f"Kattappa execution loop completed. Plan steps: {executed_steps}."
        }
