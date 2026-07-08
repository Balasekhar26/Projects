"""Cognitive Orchestrator Engine (Program 8).

Coordinates the global continuous loops connecting Planner, Scheduler,
Executor, Reflection, and Learning subsystems.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.core.integration.events import CognitiveEvent, generate_trace_id, generate_session_id
from backend.core.integration.tracing import CognitiveTracer
from backend.core.planning.task import Plan, Operator
from backend.core.planning.plan_graph import PlanCompiler
from backend.core.execution.execution_engine import ExecutionEngine
from backend.core.execution.execution_state import ExecutionState
from backend.core.reflection.models import ExecutionRecord
from backend.core.reflection.reflection_engine import ReflectionEngine
from backend.core.learning.learning_engine import LearningEngine

logger = logging.getLogger(__name__)


class CognitiveOrchestrator:
    """Master orchestrator unifying Kattappa's OODA loops feedback architecture."""

    _instance: Optional[CognitiveOrchestrator] = None

    def __init__(self) -> None:
        self.tracer = CognitiveTracer.get_instance()
        self.execution_engine = ExecutionEngine()
        self.reflection_engine = ReflectionEngine.get_instance()
        self.learning_engine = LearningEngine.get_instance()

    @classmethod
    def get_instance(cls) -> CognitiveOrchestrator:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def run_cognitive_loop(
        self,
        plan_id: str,
        steps: List[Operator],
        initial_variables: Dict[str, Any],
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """Runs the end-to-end cognitive loop: Plan -> Execute -> Reflect -> Learn -> Memory update."""
        trace_id = generate_trace_id()
        session_id = generate_session_id()

        logger.info("Executing global cognitive loop. Trace: %s, Session: %s", trace_id, session_id)

        # ----------------------------------------------------------------------
        # Phase 1: Planning / DAG Compile & Scheduling
        # ----------------------------------------------------------------------
        span_planner = self.tracer.start_span(trace_id, "Planner", {"plan_id": plan_id})
        
        # Compile
        plan = Plan(plan_id=plan_id, goal_id="unknown_goal", steps=steps)
        graph = PlanCompiler.compile_plan_to_graph(plan)
        
        # In a real scheduling flow we would optimize, here compile is completed.
        self.tracer.end_span(span_planner)

        # ----------------------------------------------------------------------
        # Phase 2: Execution Engine Runtime
        # ----------------------------------------------------------------------
        span_executor = self.tracer.start_span(trace_id, "Executor", {"session_id": session_id})
        
        start_time = time.time()
        # Start stateful execution
        exec_session_id = self.execution_engine.start_execution(
            graph=graph,
            initial_variables=initial_variables,
            max_retries=max_retries,
        )
        
        # Extract execution session details
        session = self.execution_engine.sessions[exec_session_id]
        context = self.execution_engine.contexts[exec_session_id]
        total_duration = time.time() - start_time

        self.tracer.end_span(span_executor, {
            "execution_status": session.status.value,
            "completed_nodes": list(session.completed_nodes),
            "failed_nodes": list(session.failed_nodes),
        })

        # ----------------------------------------------------------------------
        # Phase 3: Reflection Engine Analysis
        # ----------------------------------------------------------------------
        span_reflection = self.tracer.start_span(trace_id, "Reflection")

        # Construct failures metadata list
        failures = []
        # If execution session ended in failure, fetch errors
        # In our simplified engine mock/run, failed nodes are logged
        for failed_node in session.failed_nodes:
            failures.append({
                "node_id": failed_node,
                "error_message": f"Execution failed on step {failed_node}",
            })

        # Compile durations map from monitor metrics
        task_durations = {}
        for completed in session.completed_nodes:
            task_durations[completed] = context.outputs.get(completed, {}).get("duration", 1.0)

        record = ExecutionRecord(
            session_id=session_id,
            plan_id=plan_id,
            status=session.status.value,
            total_duration=total_duration,
            task_durations=task_durations,
            retries=dict(session.retry_counts),
            failures=failures,
            variables_snapshot=dict(context.variables),
            outputs=dict(context.outputs),
        )

        # Process reflection review & candidates
        review = self.reflection_engine.process_execution(record)
        candidates = self.reflection_engine.get_candidates(session_id)

        self.tracer.end_span(span_reflection, {
            "success_rate": review.success_rate,
            "failure_category": review.failure_category,
            "candidates_count": len(candidates),
        })

        # ----------------------------------------------------------------------
        # Phase 4: Learning & Memory update
        # ----------------------------------------------------------------------
        span_learning = self.tracer.start_span(trace_id, "Learning")
        
        applied_candidates = []
        pending_candidates = []

        for candidate in candidates:
            # Submit candidate to safety, confidence, and conflict checks
            processed = self.learning_engine.submit_candidate(candidate, evidence_count=5)
            if processed.status == "Applied":
                applied_candidates.append(processed.candidate_id)
            else:
                pending_candidates.append(processed.candidate_id)

        self.tracer.end_span(span_learning, {
            "applied_count": len(applied_candidates),
            "pending_count": len(pending_candidates),
        })

        # Record standard cognitive loop finish event
        self.tracer.record_event(
            CognitiveEvent(
                session_id=session_id,
                execution_id=exec_session_id,
                trace_id=trace_id,
                source="Orchestrator",
                event_type="CognitiveLoopCompleted",
                payload={
                    "status": "Success" if session.status == ExecutionState.COMPLETED else "Failed",
                    "applied_learnings": applied_candidates,
                    "pending_approvals": pending_candidates,
                }
            )
        )

        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "execution_status": session.status.value,
            "success_rate": review.success_rate,
            "failure_category": review.failure_category,
            "applied_learnings": applied_candidates,
            "pending_approvals": pending_candidates,
            "active_configuration": dict(self.learning_engine.consolidator.active_config),
        }
