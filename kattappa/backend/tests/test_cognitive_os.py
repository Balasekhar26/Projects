"""Integration tests for the Kattappa Cognitive Operating System (COS) Architecture."""
from __future__ import annotations

import pytest
from backend.core.cos.kernel import KERNEL
from backend.core.context_manager import ContextManager
from backend.core.executive_workspace import WORKSPACE
from backend.core.conflict_resolver import ConflictResolver
from backend.core.memory_consolidator import MemoryConsolidator
from backend.core.simulation_engine import SimulationEngine
from backend.core.emotion_layer import EmotionLayer
from backend.core.self_model import SelfModel
from backend.core.agent_reputation import AgentReputationTracker
from backend.core.tool_reliability import ToolReliabilityTracker
from backend.core.graph import _get_kg
from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
from backend.core.orchestrator.base import Task
from backend.core.orchestrator.context import SharedContext
from backend.core.goal_hierarchy import HierarchyLevel

@pytest.fixture(autouse=True)
def clean_databases():
    # Clean consolidation buffers
    MemoryConsolidator.reset()
    # Clean reput/reliability stats
    AgentReputationTracker.reset()
    ToolReliabilityTracker.reset()
    # Clean workspace registers
    WORKSPACE.reset_workspace()
    # Clean emotion states
    EmotionLayer.reset()
    yield


def test_cognitive_kernel_routing():
    # 1. Event pub/sub routing
    events_triggered = []
    KERNEL.events.subscribe("test_topic", lambda p: events_triggered.append(p))
    KERNEL.events.publish("test_agent", "test_topic", {"data": "ok"})
    assert len(events_triggered) == 1
    assert events_triggered[0].payload["data"] == "ok"

    # 2. Goal creation routing
    gid = KERNEL.goals.add_goal("g_kernel_test", None, HierarchyLevel.GOAL, "Kernel Goal", "Description")
    assert gid is not None
    progress = KERNEL.goals.get_progress(gid)
    assert progress == 0.0


def test_context_manager_compilation():
    session_id = "test_context_session"
    ctx = ContextManager.build_execution_context(session_id, "debugging radar issues")
    assert ctx["session_id"] == session_id
    assert "compiled_context" in ctx
    assert "System Environment" in ctx["compiled_context"]


def test_executive_workspace_registers():
    WORKSPACE.write_scratchpad("temp_code", "print(123)")
    assert WORKSPACE.read_scratchpad("temp_code") == "print(123)"

    WORKSPACE.push_reasoning("step 1: fetch data")
    WORKSPACE.push_reasoning("step 2: analyze")
    assert WORKSPACE.pop_reasoning() == "step 2: analyze"

    WORKSPACE.enqueue_thought("Observation: latency spiked")
    assert WORKSPACE.dequeue_thought() == "Observation: latency spiked"

    WORKSPACE.set_register("cpu_affinity", 2)
    assert WORKSPACE.get_register("cpu_affinity") == 2


def test_conflict_resolver_priority():
    # Test case 1: Wisdom halts execution
    wisdom = {"block_action": True, "reason": "Violates core values"}
    dec = ConflictResolver.resolve({}, {}, {}, wisdom)
    assert dec.action == "HALT"
    assert dec.dominant_factor == "WISDOM"

    # Test case 2: World model risk overrides planner
    risk_severe = {"risk_score": 0.90, "risk_description": "Critical danger"}
    dec = ConflictResolver.resolve({"action": "PROCEED"}, risk_severe, {})
    assert dec.action == "HALT"
    assert dec.dominant_factor == "SAFETY_RISK"

    # Test case 3: Scientist uncertainty degrades plan
    sci_uncertain = {"p_survival": 0.85, "details": "Low evidence"}
    dec = ConflictResolver.resolve({"action": "PROCEED", "confidence": 0.9}, {"risk_score": 0.1}, sci_uncertain)
    assert dec.action == "DEGRADE_PLAN"
    assert dec.dominant_factor == "SCIENTIST_UNCERTAINTY"


def test_memory_consolidator_promotions():
    # 1. High-significance fact should be promoted to Semantic Store
    MemoryConsolidator.stage_transient_fact("session_a", "Highly important semantic observation", significance=0.85)
    # 2. Low-significance fact should be discarded to episodic logs
    MemoryConsolidator.stage_transient_fact("session_a", "Minor temp observation", significance=0.20)
    
    stats = MemoryConsolidator.consolidate(significance_floor=0.50)
    assert stats["promoted"] == 1
    assert stats["discarded"] == 1


def test_temporal_graph_validity():
    kg = _get_kg()
    if kg is not None:
        # Clear nodes
        with kg._store._lock:
            conn = kg._store._get_conn()
            conn.execute("DELETE FROM kg_nodes")
            conn.execute("DELETE FROM kg_edges")
            conn.commit()
            conn.close()

        # Add node with validity range
        node = kg.add_node(
            name="radar_subsystem",
            entity_type="COMPONENT",
            valid_from="2026-06-01",
            valid_until="2026-07-01"
        )
        assert node.valid_from == "2026-06-01"
        assert node.valid_until == "2026-07-01"


def test_simulation_engine_routing():
    plans = [
        {
            "id": "plan_safe",
            "steps": [{"action": "read_file", "params": {"path": "/tmp/a"}}]
        },
        {
            "id": "plan_risky",
            "steps": [
                {"action": "shell_execute", "params": {"cmd": "rm -rf /"}},
                {"action": "delete_file", "params": {"path": "/tmp/b"}}
            ]
        }
    ]
    
    best = SimulationEngine.get_best_plan(plans, {})
    assert best is not None
    assert best["id"] == "plan_safe"
    assert best["simulation"]["expected_utility"] > 0.5


def test_emotion_and_self_model():
    # Emotion state scaling
    EmotionLayer.set_user_state("stressed", intensity=0.8)
    adj = EmotionLayer.get_style_adjustments()
    assert adj["empathy_factor"] >= 0.5
    assert adj["response_delay_seconds"] > 0.0

    # Self capability checks
    allowed, score, reason = SelfModel.evaluate_capability("calculate 1 + 1")
    assert allowed
    assert score > 0.5

    # Unsupported check
    allowed_bad, score_bad, reason_bad = SelfModel.evaluate_capability("train image model on gpu")
    assert not allowed_bad
    assert "Unsupported capability" in reason_bad


def test_reputation_and_reliability():
    # Record agent metrics
    AgentReputationTracker.record_execution("coder", success=True, latency=0.2)
    AgentReputationTracker.record_execution("coder", success=False, latency=0.8)
    rep = AgentReputationTracker.get_reputation("coder")
    assert rep["success_rate"] == 0.5
    assert rep["average_latency"] == 0.5

    # Record tool metrics
    ToolReliabilityTracker.record_invocation("terminal", success=True, latency=0.1)
    ToolReliabilityTracker.record_invocation("terminal", success=False, latency=0.5, error="Timeout")
    rel = ToolReliabilityTracker.get_reliability("terminal")
    assert rel["success_rate"] == 0.5
    assert rel["last_error"] == "Timeout"


def test_executive_ceo_integration():
    agent = ORCHESTRATOR_REGISTRY.get("executive")
    assert agent is not None
    
    # 1. Test nominal proceeding path
    task_proceed = Task(
        task_id="task_ceo_proceed",
        agent_name="executive",
        action="execute",
        params={"message": "debugging radar issues"}
    )
    context = SharedContext()
    res = agent.execute(task_proceed, context)
    assert res.success
    assert res.output["decision"] == "PROCEED"
    
    # 2. Test self boundary halt path
    task_halt = Task(
        task_id="task_ceo_halt",
        agent_name="executive",
        action="execute",
        params={"message": "train image model on gpu"}
    )
    res_halt = agent.execute(task_halt, context)
    assert not res_halt.success
    assert "Unsupported capability" in res_halt.error
