"""Tests for Phase K15: Skill Learning (Procedural memory failure logging)."""
from __future__ import annotations

import json
import pytest
from backend.core.procedural_memory import ProceduralMemory
from backend.core.cognitive_memory_bus import MEMORY_BUS
from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
from backend.core.orchestrator.base import Task
from backend.core.orchestrator.context import SharedContext


@pytest.fixture(autouse=True)
def clean_procedural_db():
    conn = ProceduralMemory._get_sqlite_conn()
    conn.execute("DELETE FROM hm_procedures")
    conn.execute("DELETE FROM hm_procedure_audit")
    conn.commit()
    conn.close()
    yield


def test_register_failed_procedure():
    # 1. Register a failed procedure via memory bus
    steps = [{"step": 1, "action": "send_request"}, {"step": 2, "action": "wait_response"}]
    res = MEMORY_BUS.write(
        memory_type="procedural",
        data={
            "skill_name": "fetch_api_data",
            "trigger_phrase": "fetch endpoint data",
            "steps": steps,
            "trust_level": "FAILED_EXAMPLE",
            "failure_reason": "Timeout waiting for endpoint response",
        },
        confidence=0.95,
        verified=True
    )
    
    assert res.success
    assert res.record_id is not None
    
    # 2. Retrieve procedure and verify attributes
    proc = ProceduralMemory.get_procedure(res.record_id)
    assert proc is not None
    assert proc["skill_name"] == "fetch_api_data"
    assert proc["trust_level"] == "FAILED_EXAMPLE"
    assert proc["failure_reason"] == "Timeout waiting for endpoint response"
    
    # Verify steps_json contains correct serialized steps
    retrieved_steps = json.loads(proc["steps_json"])
    assert len(retrieved_steps) == 2
    assert retrieved_steps[0]["action"] == "send_request"


def test_failed_procedure_execution_gating():
    # Register failed procedure
    steps = [{"step": 1, "action": "parse_args"}]
    pid = ProceduralMemory.register_procedure(
        skill_name="arguments_parse",
        trigger_phrase="parse CLI args",
        steps_json=json.dumps(steps),
        trust_level="FAILED_EXAMPLE",
        failure_reason="Invalid flags supplied",
    )
    
    # Call validate_and_gate
    allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="user")
    # Should be blocked
    assert not allowed
    assert reason == "trust_level_not_allowed"


def test_memory_keeper_agent_procedural_failure_write():
    agent = ORCHESTRATOR_REGISTRY.get("memory keeper")
    assert agent is not None
    
    steps = [{"step": 1, "action": "open_socket"}]
    task = Task(
        task_id="task_mk_procedural_write",
        agent_name="memory keeper",
        action="write",
        params={
            "action": "write",
            "memory_type": "procedural",
            "verified": True,
            "confidence": 0.95,
            "data": {
                "skill_name": "network_connect",
                "steps": steps,
                "trust_level": "FAILED_EXAMPLE",
                "failure_reason": "Connection refused",
            }
        }
    )
    
    context = SharedContext()
    res = agent.execute(task, context)
    assert res.success
    assert res.output["record_id"] is not None
    
    # Verify via DB
    proc = ProceduralMemory.get_procedure(res.output["record_id"])
    assert proc is not None
    assert proc["trust_level"] == "FAILED_EXAMPLE"
    assert proc["failure_reason"] == "Connection refused"
