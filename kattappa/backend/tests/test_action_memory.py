from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def isolated_action_memory(tmp_path, monkeypatch):
    import backend.core.action_memory as action_memory_module

    monkeypatch.setattr(action_memory_module, "runtime_data_root", lambda: tmp_path)
    return action_memory_module.ActionMemory


def test_empty_action_memory_returns_safe_defaults(isolated_action_memory):
    assert isolated_action_memory.get_recent_actions() == []
    stats = isolated_action_memory.get_agent_statistics("browser").to_dict()
    assert stats["total_actions"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["avg_duration_ms"] == 0.0


def test_insert_action_stores_required_fields_and_tags(isolated_action_memory):
    action_id = isolated_action_memory.record(
        action_id="act_insert",
        workflow_id="wf_insert",
        parent_action_id="act_parent",
        agent="browser",
        action="SEARCH_WEB",
        reason="Find RF design reference",
        expected_outcome="Reference located",
        actual_outcome="Reference located",
        success=True,
        duration_ms=1320,
        confidence_score=0.97,
        rollback_executed=False,
        rollback_action_id="",
        rollback_chain_id="rb_chain_1",
        tags=["Browser", "web", "rf", "web"],
        timestamp="2026-06-23T12:30:10Z",
    )

    record = isolated_action_memory.get_action(action_id)
    assert record is not None
    payload = record.to_dict()
    assert payload["action_id"] == "act_insert"
    assert payload["workflow_id"] == "wf_insert"
    assert payload["parent_action_id"] == "act_parent"
    assert payload["action"] == "SEARCH_WEB"
    assert payload["reason"] == "Find RF design reference"
    assert payload["outcome"] == "Reference located"
    assert payload["success"] is True
    assert payload["failure"] is False
    assert payload["duration_ms"] == 1320
    assert payload["confidence_score"] == 0.97
    assert payload["rollback_chain_id"] == "rb_chain_1"
    assert payload["timestamp"] == "2026-06-23T12:30:10Z"
    assert payload["tags"] == ["browser", "web", "rf"]


def test_duplicate_action_id_is_rejected(isolated_action_memory):
    isolated_action_memory.record(
        action_id="act_duplicate",
        agent="coder",
        action="CREATE_FILE",
    )

    with pytest.raises(ValueError, match="action_id already exists"):
        isolated_action_memory.record(
            action_id="act_duplicate",
            agent="coder",
            action="CREATE_FILE",
        )


def test_update_outcome_appends_immutable_child_event(isolated_action_memory):
    isolated_action_memory.record(
        action_id="act_update",
        workflow_id="wf_update",
        agent="file",
        action="CREATE_FILE",
        success=False,
        actual_outcome="File missing",
        duration_ms=500,
        tags=["file", "failed"],
    )

    updated = isolated_action_memory.update_outcome(
        "act_update",
        actual_outcome="File created after retry",
        success=True,
        duration_ms=710,
        confidence_score=0.91,
        rollback_executed=True,
        tags=["file", "retry", "success"],
    )

    assert updated is True
    original = isolated_action_memory.get_action("act_update")
    assert original is not None
    assert original.actual_outcome == "File missing"
    assert original.success is False

    workflow_items = isolated_action_memory.get_workflow_actions("wf_update")
    assert len(workflow_items) == 2
    child = workflow_items[1]
    assert child.parent_action_id == "act_update"
    assert child.action == "CREATE_FILE_OUTCOME_UPDATE"
    assert child.actual_outcome == "File created after retry"
    assert child.success is True
    assert child.failure is False
    assert child.duration_ms == 710
    assert child.confidence_score == 0.91
    assert child.rollback_executed is True
    assert child.tags == ["file", "failed", "retry", "success", "outcome-update", "rollback"]


def test_workflow_and_rollback_lineage_retrieval(isolated_action_memory):
    isolated_action_memory.record(
        action_id="act_lineage_parent",
        workflow_id="wf_lineage",
        agent="coder",
        action="WRITE_FILE",
        success=True,
        rollback_chain_id="rollback_chain_alpha",
    )
    isolated_action_memory.record(
        action_id="act_lineage_rollback",
        workflow_id="wf_lineage",
        parent_action_id="act_lineage_parent",
        agent="coder",
        action="DELETE_FILE",
        success=True,
        rollback_executed=True,
        rollback_action_id="act_lineage_parent",
        rollback_chain_id="rollback_chain_alpha",
    )

    items = isolated_action_memory.get_workflow_actions("wf_lineage")
    assert [item.action_id for item in items] == ["act_lineage_parent", "act_lineage_rollback"]
    assert items[1].parent_action_id == "act_lineage_parent"
    assert items[1].rollback_action_id == "act_lineage_parent"
    assert items[1].rollback_chain_id == "rollback_chain_alpha"


def test_storage_validation_rejects_bad_values(isolated_action_memory):
    with pytest.raises(ValueError, match="duration_ms"):
        isolated_action_memory.record(agent="coder", action="RUN_TESTS", duration_ms=-1)

    with pytest.raises(ValueError, match="confidence_score"):
        isolated_action_memory.record(agent="coder", action="RUN_TESTS", confidence_score=1.5)

    with pytest.raises(ValueError, match="timestamp"):
        isolated_action_memory.record(
            agent="coder",
            action="RUN_TESTS",
            timestamp="not-a-timestamp",
        )


def test_success_failure_and_similar_retrieval(isolated_action_memory):
    isolated_action_memory.record(
        action_id="act_success",
        agent="browser",
        action="SEARCH_WEB",
        success=True,
        duration_ms=100,
        confidence_score=0.9,
    )
    isolated_action_memory.record(
        action_id="act_failure",
        agent="browser",
        action="SEARCH_WEB",
        success=False,
        duration_ms=300,
        confidence_score=0.2,
        rollback_executed=True,
    )

    successes = isolated_action_memory.get_successful_actions("SEARCH_WEB")
    failures = isolated_action_memory.get_failed_actions("SEARCH_WEB")
    similar = isolated_action_memory.find_similar_actions("SEARCH_WEB")
    stats = isolated_action_memory.get_action_type_statistics("SEARCH_WEB")

    assert [item.action_id for item in successes] == ["act_success"]
    assert [item.action_id for item in failures] == ["act_failure"]
    assert {item.action_id for item in similar} == {"act_success", "act_failure"}
    assert stats["total_executions"] == 2
    assert stats["success_count"] == 1
    assert stats["failure_count"] == 1
    assert stats["success_rate"] == 0.5
    assert stats["avg_duration_ms"] == 200.0
    assert stats["rollback_count"] == 1


def test_agent_statistics_support_strategy_lookup(isolated_action_memory):
    isolated_action_memory.record(
        agent="desktop",
        action="DESKTOP_OPEN_APP",
        success=True,
        duration_ms=100,
        confidence_score=0.9,
    )
    isolated_action_memory.record(
        agent="desktop",
        action="DESKTOP_OPEN_APP",
        success=False,
        duration_ms=300,
        confidence_score=0.3,
        rollback_executed=True,
    )

    stats = isolated_action_memory.get_agent_statistics("desktop").to_dict()
    assert stats["total_actions"] == 2
    assert stats["success_count"] == 1
    assert stats["failure_count"] == 1
    assert stats["success_rate"] == 0.5
    assert stats["avg_duration_ms"] == 200.0
    assert stats["rollback_rate"] == 0.5


def test_large_history_recent_query(isolated_action_memory):
    for index in range(250):
        isolated_action_memory.record(
            action_id=f"act_bulk_{index}",
            agent="coder",
            action="RUN_TESTS",
            success=index % 5 != 0,
            duration_ms=index,
        )

    recent = isolated_action_memory.get_recent_actions(limit=10)
    assert len(recent) == 10
    assert isolated_action_memory.count_total() == 250


def test_broker_records_verified_action_memory(tmp_path, monkeypatch, isolated_action_memory):
    from backend.core.action_broker import ActionBroker

    monkeypatch.setattr(
        ActionBroker,
        "AUDIT_LOG_PATH",
        str(tmp_path / "action_broker_audit.log"),
    )
    state = {"user_input": "List the project directory", "logs": []}
    result = ActionBroker.intake_request(
        "coder",
        "LIST_DIR",
        {"target": str(tmp_path)},
        state,
    )

    assert result["success"] is True
    assert result["action_memory_id"]
    record = isolated_action_memory.get_action(result["action_memory_id"])
    assert record is not None
    assert record.agent == "coder"
    assert record.action == "LIST_DIR"
    assert record.success is True


def test_record_from_broker_preserves_exact_dve_confidence(isolated_action_memory):
    from backend.core.action_memory import record_from_broker

    action_id = record_from_broker(
        agent_name="browser",
        action="BROWSER_SEARCH",
        params={"query": "rf design", "reason": "Find RF reference"},
        execution_result={"success": True, "message": "Reference located"},
        dve_result={"success": True, "confidence_score": 0.72, "outcome": "REVIEW"},
        duration_ms=321,
        state={"workflow_id": "wf_dve"},
    )

    assert action_id is not None
    record = isolated_action_memory.get_action(action_id)
    assert record is not None
    assert record.confidence_score == 0.72
    assert record.workflow_id == "wf_dve"


def test_action_memory_http_create_and_get(isolated_action_memory):
    client = TestClient(app)
    response = client.post(
        "/action-memory/actions",
        json={
            "action_id": "act_http",
            "workflow_id": "wf_http",
            "agent": "browser",
            "action": "SEARCH_WEB",
            "reason": "Find a reference",
            "outcome": "Reference found",
            "success": True,
            "duration_ms": 42,
            "confidence_score": 0.95,
            "tags": ["browser", "search"],
        },
    )
    assert response.status_code == 200
    assert response.json()["item"]["action_id"] == "act_http"
    assert response.json()["item"]["workflow_id"] == "wf_http"

    fetched = client.get("/action-memory/actions/act_http")
    assert fetched.status_code == 200
    assert fetched.json()["item"]["outcome"] == "Reference found"


def test_action_memory_http_duplicate_and_validation(isolated_action_memory):
    client = TestClient(app)
    payload = {
        "action_id": "act_http_duplicate",
        "agent": "coder",
        "action": "RUN_TESTS",
        "success": True,
    }

    assert client.post("/action-memory/actions", json=payload).status_code == 200
    duplicate = client.post("/action-memory/actions", json=payload)
    assert duplicate.status_code == 400

    invalid = client.post(
        "/action-memory/actions",
        json={
            "agent": "coder",
            "action": "RUN_TESTS",
            "success": True,
            "failure": True,
        },
    )
    assert invalid.status_code == 400


def test_action_memory_http_retrieval_apis(isolated_action_memory):
    client = TestClient(app)
    for payload in [
        {
            "action_id": "act_http_ok",
            "agent": "browser",
            "action": "SEARCH_WEB",
            "success": True,
            "duration_ms": 100,
        },
        {
            "action_id": "act_http_fail",
            "agent": "browser",
            "action": "SEARCH_WEB",
            "failure": True,
            "duration_ms": 300,
            "rollback_executed": True,
        },
    ]:
        response = client.post("/action-memory/actions", json=payload)
        assert response.status_code == 200

    recent = client.get("/action-memory/actions/recent", params={"limit": 2})
    successful = client.get(
        "/action-memory/actions/successful",
        params={"action_type": "SEARCH_WEB", "agent": "browser"},
    )
    failed = client.get(
        "/action-memory/actions/failed",
        params={"action_type": "SEARCH_WEB", "agent": "browser"},
    )
    similar = client.get(
        "/action-memory/actions/similar",
        params={"action": "SEARCH_WEB", "agent": "browser"},
    )
    stats = client.get("/action-memory/agents/browser/statistics")

    assert recent.status_code == 200
    assert len(recent.json()["items"]) == 2
    assert [item["action_id"] for item in successful.json()["items"]] == ["act_http_ok"]
    assert [item["action_id"] for item in failed.json()["items"]] == ["act_http_fail"]
    assert similar.json()["success_rate"] == 0.5
    assert similar.json()["avg_duration_ms"] == 200.0
    assert stats.json()["item"]["rollback_rate"] == 0.5


def test_action_memory_http_patch_appends_child_record(isolated_action_memory):
    client = TestClient(app)
    client.post(
        "/action-memory/actions",
        json={
            "action_id": "act_http_patch",
            "workflow_id": "wf_http_patch",
            "agent": "file",
            "action": "CREATE_FILE",
            "failure": True,
            "outcome": "Missing file",
            "duration_ms": 80,
        },
    )

    response = client.patch(
        "/action-memory/actions/act_http_patch",
        json={
            "success": True,
            "outcome": "Created file",
            "duration_ms": 120,
            "confidence_score": 0.88,
            "tags": ["file", "retry"],
        },
    )

    assert response.status_code == 200
    assert response.json()["appended"] is True
    assert response.json()["parent_action_id"] == "act_http_patch"
    item = response.json()["item"]
    assert item["parent_action_id"] == "act_http_patch"
    assert item["action"] == "CREATE_FILE_OUTCOME_UPDATE"
    assert item["success"] is True
    assert item["failure"] is False
    assert item["outcome"] == "Created file"
    assert item["duration_ms"] == 120
    assert item["tags"] == ["file", "retry", "outcome-update"]

    original = client.get("/action-memory/actions/act_http_patch").json()["item"]
    assert original["outcome"] == "Missing file"


def test_action_memory_db_file_is_created_under_runtime_root(
    tmp_path, monkeypatch, isolated_action_memory
):
    isolated_action_memory.record(
        action_id="act_db_path",
        agent="coder",
        action="RUN_TESTS",
        success=True,
    )

    db_path = Path(tmp_path) / "backend" / "data" / "action_memory.db"
    assert db_path.exists()
    assert db_path.stat().st_size > 0
