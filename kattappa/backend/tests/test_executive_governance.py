from __future__ import annotations

import sqlite3
import pytest
import tempfile
from pathlib import Path

from backend.core.executive_governance import ExecutiveCortex


@pytest.fixture
def temp_config_db(monkeypatch, tmp_path):
    from backend.core.config import load_config
    cfg = load_config()
    from dataclasses import replace
    new_cfg = replace(cfg, sqlite_path=tmp_path / "kattappa_ai_os.db")
    monkeypatch.setattr("backend.core.executive_governance.load_config", lambda: new_cfg)
    yield tmp_path


def test_priority_attention_floor_gating(temp_config_db):
    # Case A: Low priority task (W < 0.3)
    res_low = ExecutiveCortex.arbitrate_task(
        task_id="task_1",
        task_name="Low Priority Task",
        priority=0.1,
        urgency=0.2,
        token_budget=1000,
        max_execution_seconds=60,
    )
    # W = 0.1 * 0.6 + 0.2 * 0.4 = 0.06 + 0.08 = 0.14 < 0.3 -> PAUSE
    assert res_low["weight"] == 0.14
    assert res_low["action"] == "PAUSE"
    assert res_low["state"] == "BLOCKED"

    # Case B: High priority task (W >= 0.3)
    res_high = ExecutiveCortex.arbitrate_task(
        task_id="task_2",
        task_name="High Priority Task",
        priority=0.6,
        urgency=0.8,
        token_budget=1000,
        max_execution_seconds=60,
    )
    # W = 0.6 * 0.6 + 0.8 * 0.4 = 0.36 + 0.32 = 0.68 >= 0.3 -> PROCEED
    assert res_high["weight"] == 0.68
    assert res_high["action"] == "PROCEED"
    assert res_high["state"] == "QUEUED"


def test_loop_thrashing_protection(temp_config_db):
    # Initialize task
    ExecutiveCortex.arbitrate_task(
        task_id="task_thrash",
        task_name="Thrashing Task",
        priority=0.8,
        urgency=0.8,
        token_budget=1000,
        max_execution_seconds=60,
    )

    # Increment replan count up to 3 (normal operations allowed)
    for i in range(3):
        res = ExecutiveCortex.replan_increment("task_thrash")
        assert res["replan_count"] == i + 1
        assert res["action"] == "PROCEED"

    # 4th increment exceeds the thrashing threshold of 3 -> ABORT
    res_abort = ExecutiveCortex.replan_increment("task_thrash")
    assert res_abort["replan_count"] == 4
    assert res_abort["action"] == "ABORT"
    assert res_abort["state"] == "BLOCKED"


def test_resource_budget_ceilings(temp_config_db):
    # Initialize task
    ExecutiveCortex.arbitrate_task(
        task_id="task_resource",
        task_name="Resource Task",
        priority=0.8,
        urgency=0.8,
        token_budget=1000,
        max_execution_seconds=60,
    )

    # Consume normal amount (within limit)
    res_ok = ExecutiveCortex.record_resource_consumption(
        task_id="task_resource",
        resource_type="tokens",
        amount=50.0,
        daily_limit=100.0,
    )
    assert res_ok["action"] == "PROCEED"
    assert res_ok["total_today"] == 50.0

    # Consume again to exceed limit
    res_exceed = ExecutiveCortex.record_resource_consumption(
        task_id="task_resource",
        resource_type="tokens",
        amount=60.0,
        daily_limit=100.0,
    )
    assert res_exceed["action"] == "HUMAN_APPROVAL_REQUIRED"
    assert res_exceed["total_today"] == 110.0


def test_reviewer_agreement_tracking(temp_config_db):
    # First arbitrate/initialize tasks to satisfy FOREIGN KEY constraint
    ExecutiveCortex.arbitrate_task(
        task_id="task_t1",
        task_name="Task 1",
        priority=0.8,
        urgency=0.8,
        token_budget=1000,
        max_execution_seconds=60,
    )
    ExecutiveCortex.arbitrate_task(
        task_id="task_t2",
        task_name="Task 2",
        priority=0.8,
        urgency=0.8,
        token_budget=1000,
        max_execution_seconds=60,
    )

    # Log congruent decision
    stats1 = ExecutiveCortex.record_reviewer_decision(
        reviewer_id="human_1",
        task_id="task_t1",
        recommendation="APPROVE",
        decision="APPROVE",
    )
    assert stats1["congruent"] is True
    assert stats1["agreement_rate"] == 1.0

    # Log non-congruent decision
    stats2 = ExecutiveCortex.record_reviewer_decision(
        reviewer_id="human_1",
        task_id="task_t2",
        recommendation="APPROVE",
        decision="REJECT",
    )
    assert stats2["congruent"] is False
    assert stats2["agreement_rate"] == 0.5


def test_api_endpoints(temp_config_db):
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    
    # 1. Arbitrate task
    payload = {
        "task_id": "api_task_1",
        "task_name": "API Arbitrated Task",
        "priority": 0.8,
        "urgency": 0.8,
        "token_budget": 5000,
        "max_execution_seconds": 120
    }
    response = client.post("/executive/arbitrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "api_task_1"
    assert data["weight"] == 0.8
    assert data["action"] == "PROCEED"
    
    # 2. Review task
    review_payload = {
        "reviewer_id": "human_tester",
        "task_id": "api_task_1",
        "recommendation": "APPROVE",
        "decision": "APPROVE"
    }
    response = client.post("/executive/review", json=review_payload)
    assert response.status_code == 200
    review_data = response.json()
    assert review_data["reviewer_id"] == "human_tester"
    assert review_data["congruent"] is True
    assert review_data["agreement_rate"] == 1.0

    # 3. Status endpoint
    response = client.get("/executive/status")
    assert response.status_code == 200
    status_data = response.json()
    assert status_data["status"] == "active"
    assert status_data["total_tasks"] >= 1
