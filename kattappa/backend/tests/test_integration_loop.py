"""Unit and integration tests for Program 8: Cognitive Integration Layer.
"""
from __future__ import annotations

import pytest

from backend.core.integration.events import generate_trace_id, generate_session_id
from backend.core.integration.tracing import CognitiveTracer
from backend.core.integration.orchestrator import CognitiveOrchestrator
from backend.core.planning.task import Operator


def test_id_standards_generation():
    """Checks that standardized trace and session IDs are properly formatted."""
    trace_id = generate_trace_id()
    session_id = generate_session_id()

    assert trace_id.startswith("tr_")
    assert session_id.startswith("sess_")
    assert len(trace_id) == 11
    assert len(session_id) == 13


def test_distributed_tracing_spans():
    """Verifies that CognitiveTracer starts, ends, and records timing logs of cross-module spans."""
    tracer = CognitiveTracer.get_instance()
    trace_id = generate_trace_id()

    span_p = tracer.start_span(trace_id, "Planner")
    span_e = tracer.start_span(trace_id, "Executor")
    tracer.end_span(span_p)
    tracer.end_span(span_e)

    history = tracer.get_trace_history(trace_id)
    assert len(history) == 2
    assert history[0]["source"] == "Planner"
    assert history[1]["source"] == "Executor"


def test_e2e_successful_cognitive_loop():
    """Integration test: runs successful plan steps sequence and checks completed statuses."""
    orchestrator = CognitiveOrchestrator.get_instance()
    
    op_clean = Operator("clean", "CleanTempDir", effects={"temp_cleaned": True})
    
    result = orchestrator.run_cognitive_loop(
        plan_id="plan_clean",
        steps=[op_clean],
        initial_variables={"temp_cleaned": False},
        max_retries=1,
    )

    assert result["execution_status"] == "Completed"
    assert result["success_rate"] == 100.0
    assert result["failure_category"] is None
    assert len(result["applied_learnings"]) == 0
    assert len(result["pending_approvals"]) == 0


def test_e2e_failed_adaptation_feedback_loop():
    """Integration test: failing execution triggers failure classification and learning recommendations."""
    orchestrator = CognitiveOrchestrator.get_instance()
    
    # Operator configured to fail to simulate API rate limit
    op_api = Operator(
        operator_id="call_api",
        name="CallExternalAPI",
        parameters={"fail_execution": True},
    )

    result = orchestrator.run_cognitive_loop(
        plan_id="plan_api",
        steps=[op_api],
        initial_variables={},
        max_retries=1,
    )

    assert result["execution_status"] == "Failed"
    assert result["success_rate"] == 0.0
    assert result["failure_category"] in {"Tool", "Unknown", "API"}

