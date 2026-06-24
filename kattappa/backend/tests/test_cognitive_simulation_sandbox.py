# test_cognitive_simulation_sandbox.py
# ======================================
# Unit and integration tests for Refined LIS weights,
# Assistant Intent Validator, and Cognitive Simulation Sandbox (CSS).

from __future__ import annotations

import time
import pytest

from backend.core.consensus_engine import (
    AgentOutput,
    ConsensusEngine,
    ConsensusStatus,
    Decision,
    Recommendation,
    DecisionContext,
)
from backend.core.identity_system import IdentitySystem
from backend.core.goal_memory import GoalMemory
from backend.core.project_memory import ProjectMemory
from backend.core.cognitive_simulation_sandbox import (
    CognitiveSimulationSandbox,
    VerificationPredictionEngine,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    # Make sure we have a clean DB state before each test
    conn = GoalMemory._get_sqlite_conn()
    try:
        GoalMemory._ensure_schema(conn)
        ProjectMemory._ensure_schema(conn)
        
        # Clean LIS tables to isolate from other test modules
        conn.execute("DELETE FROM lis_drift_tracker")
        conn.execute("DELETE FROM lis_role_logs")
        conn.execute("DELETE FROM lis_identity_ledger")
        conn.execute("DELETE FROM lis_value_checks")
        conn.execute("DELETE FROM lis_identity_metrics")
        conn.execute("DELETE FROM lis_identity_profile")
        
        # Seed default profile clean
        now = time.time()
        conn.execute(
            "INSERT INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) VALUES (?, ?, ?, ?)",
            ("default_profile", "EXEMPLARY", 100.0, now)
        )
        conn.execute(
            "INSERT INTO lis_identity_metrics (profile_id, rolling_truth_index, rolling_alignment_index, rolling_reliability_index, rolling_learning_index, rolling_creativity_index, updated_at) VALUES (?, 100.0, 100.0, 100.0, 100.0, 100.0, ?)",
            ("default_profile", now)
        )
        
        conn.execute("DELETE FROM projects")
        conn.execute("DELETE FROM goals")
        conn.commit()
    finally:
        conn.close()


def test_four_role_dynamic_weights():
    # Domain specific matched to Builder
    weights = IdentitySystem.derive_role_weights({"domain": "execute and deploy"})
    
    # Assistant must not be in dynamic weights
    assert "Assistant" not in weights
    
    # Four roles must be present
    assert set(weights.keys()) == {"Teacher", "Engineer", "Scientist", "Builder"}
    
    # Matched role must meet floor bounds
    assert weights["Builder"] >= 0.35
    assert weights["Builder"] <= 0.70
    
    # Other roles must meet the non-matched floor limits
    for role in ("Teacher", "Engineer", "Scientist"):
         assert weights[role] >= 0.15

    assert sum(weights.values()) == pytest.approx(1.0)


def test_assistant_intent_validator_veto_by_agent():
    # Mock output where the Assistant agent votes REJECT due to intent mismatch
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1", recommendations=(Recommendation("Engineer", "Do X", 0.9),)),
        AgentOutput("Assistant", Decision.REJECT, source_id="m2", rationale="violates core values"),
    ]
    
    # Without intent validator: Engineer would win since Engineer has higher authority.
    # With intent validator: Assistant REJECT vetoes the decision.
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.REJECTED
    assert decision.selected is None
    assert decision.requires_human_approval is True
    assert decision.rejected_by == "AssistantIntentValidator"
    assert any("Assistant agent explicitly rejected" in r for r in decision.reasons)


def test_assistant_intent_validator_veto_by_policy():
    # Seed a project and a goal with read-only constraint in description
    goal_id = "test_goal_id"
    project_id = "test_project_id"
    now = time.time()
    
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute(
            "INSERT INTO goals (goal_id, title, description, current_state, priority_score, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (goal_id, "Analyze Logs", "Perform a read-only analysis of application logs.", "PLANNING", 8.0, now)
        )
        conn.execute(
            """
            INSERT INTO projects (
                project_id, linked_goal_id, name, title, description, status, health_status,
                calculated_priority, start_date, target_finish_date, expected_finish_date,
                completion_percent, created_at, metadata
            )
            VALUES (?, ?, ?, ?, ?, 'PROPOSED', 'GOOD', 8.0, ?, ?, ?, 0.0, ?, '{}')
            """,
            (project_id, goal_id, "Project Logs", "Project Logs", "Log study", now, now, now, now)
        )
        conn.commit()
    finally:
        conn.close()

    # The chosen recommendation proposes to WRITE or MODIFY configuration
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1", recommendations=(Recommendation("Engineer", "Write updates to config.json", 0.9),)),
    ]
    
    # Run decider with context linked to this project
    context = DecisionContext(project=project_id)
    decision = ConsensusEngine.decide(outputs, context)
    
    # Should be rejected because "write" contradicts "read-only" policy in the goal
    assert decision.status is ConsensusStatus.REJECTED
    assert decision.selected is None
    assert decision.requires_human_approval is True
    assert decision.rejected_by == "AssistantIntentValidator"
    assert any("contradicts goal policy 'read-only'" in r for r in decision.reasons)


def test_verification_prediction_heuristics():
    success_criteria = {
        "file_paths": ["/tmp/app.log"],
        "log_check_events": ["server_start"],
        "api_responses": ["https://example.com/api"]
    }
    
    # Plan missing steps to create file, write logs, or call API
    failing_plan = [
        {"action": "DUMMY_ACTION", "description": "Just do some idle waiting"}
    ]
    report = VerificationPredictionEngine.predict(success_criteria, failing_plan)
    assert report.predicted_success is False
    assert report.predicted_score == 0.0
    assert len(report.warnings) == 3
    
    # Plan containing steps addressing criteria
    passing_plan = [
        {"action": "WRITE", "description": "Write /tmp/app.log with startup event server_start"},
        {"action": "CALL_API", "description": "Fetch from https://example.com/api endpoint"}
    ]
    report_pass = VerificationPredictionEngine.predict(success_criteria, passing_plan)
    assert report_pass.predicted_success is True
    assert report_pass.predicted_score == 1.0
    assert len(report_pass.warnings) == 0


def test_css_pipeline_run():
    goal_id = "css_goal"
    now = time.time()
    
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute(
            "INSERT INTO goals (goal_id, title, description, current_state, priority_score, created_at, success_criteria) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (goal_id, "Deploy Server", "Setup server", "PLANNING", 7.0, now, '["file_exists: /var/www/index.html"]')
        )
        conn.commit()
    finally:
        conn.close()

    plan = [
        {"action": "CREATE", "description": "Create /var/www/index.html web root index"}
    ]

    pipeline_result = CognitiveSimulationSandbox.run_pipeline(
        plan_steps=plan,
        goal_id=goal_id,
        plan_title="Deploy Server Task"
    )

    assert "pipeline_id" in pipeline_result
    assert "dynamic_weights" in pipeline_result
    assert "sandbox_report" in pipeline_result
    assert "verification_prediction" in pipeline_result
    assert "consensus_decision" in pipeline_result
    assert pipeline_result["final_verdict"] == "approved"
    assert pipeline_result["requires_human_approval"] is False
