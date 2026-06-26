"""Comprehensive verification tests for Step 20 Upgrade Cognitive Thinking Pipeline v2.0."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.core.graph import run_graph, build_graph
from backend.core.world_model import WorldModel
from backend.core.metacognition import MetacognitiveGate
from backend.core.safety_review import SafetyReview


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.memory as mem_module
    import backend.core.world_model as wm_module
    import backend.core.config as config_module
    from backend.core.config import BackendConfig

    test_db = tmp_path / "kattappa_test.db"
    
    mock_config = BackendConfig(
        root=tmp_path,
        backend_root=tmp_path,
        ollama_host="http://127.0.0.1:11434",
        model_map={
            "fast": "qwen2.5:0.5b",
            "general": "qwen2.5:0.5b",
            "power": "qwen2.5:0.5b",
            "coder": "qwen2.5:0.5b",
            "vision": "qwen2.5:0.5b",
            "reasoning": "qwen2.5:0.5b",
        },
        chroma_path=tmp_path / "chroma",
        sqlite_path=test_db,
        memory_collection="kattappa_memory_test",
        shell_enabled=False,
        desktop_enabled=True,
        screen_capture_enabled=False,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=tmp_path / "screenshots",
        audio_dir=tmp_path / "audio",
        logs_dir=tmp_path / "logs",
        workspace_dir=tmp_path / "workspace",
        hardware_profile="BALANCED",
        context_budget=4096,
    )

    monkeypatch.setattr(config_module, "load_config", lambda: mock_config)
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    
    mem_module._schema_ensured = False
    WorldModel.reset()
    
    yield test_db
    WorldModel.reset()


def test_safety_on_every_path(isolated_db):
    """Verify that every execution path, including fast path / early exits, executes safety review."""
    # We will trigger a fast path query e.g. "what is today's date"
    # and mock the safety review to see if it is called.
    with patch("backend.core.safety_review.SafetyReview.review") as mock_safety_review:
        mock_safety_review.return_value = {
            "is_safe": True,
            "risk_level": 0,
            "rejection_reason": ""
        }
        
        # Run graph for a fast path input
        result = run_graph("what is today's date")
        
        # Check that safety review node was executed
        assert mock_safety_review.called, "Safety review must be executed even for fast path early exits!"
        assert any("safety review passed" in log or "safety review blocked" in log for log in result["logs"]), \
            "Logs must indicate safety review execution"


def test_reentrant_memory_recall(isolated_db):
    """Verify re-routing to memory recall with new search terms when RE_RETRIEVE is recommended."""
    
    # We mock MetacognitiveGate.verify_grounding to return RE_RETRIEVE on the first call,
    # and ANSWER on the second call.
    call_count = 0
    def mock_verify(state):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "grounded": False,
                "confidence": 0.3,
                "recommended_action": "RE_RETRIEVE",
                "new_search_query": "better query search",
                "reason": "missing critical details"
            }
        else:
            return {
                "grounded": True,
                "confidence": 0.9,
                "recommended_action": "ANSWER",
                "new_search_query": None,
                "reason": "fully grounded answers"
            }

    def mock_ask_fn(prompt, role="general", system=None):
        return json.dumps({
            "hypothesis": "standard reasoning",
            "missing_knowledge_gap": None,
            "search_query_for_gap": None
        })

    with patch("backend.core.metacognition.MetacognitiveGate.verify_grounding", side_effect=mock_verify), \
         patch("backend.core.model_router.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.metacognition.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.memory_recall.MemoryRecall.recall") as mock_recall:
         
        mock_recall.return_value = {
            "episodic_history": [],
            "semantic_context": [],
            "cognitive_episodes": [],
            "relationship_notes": {}
        }
        
        # Trigger run_graph
        result = run_graph("who wrote the codebase")
        
        # Check that recall was called twice
        assert mock_recall.call_count == 2, f"Memory recall should have been called twice (re-entrant), but got {mock_recall.call_count}"
        assert result["re_retrieve_count"] == 1
        assert result["memory_query"] == "better query search"
        assert any("re-retrieval" in log for log in result["logs"]), "Logs should show re-retrieval event"


def test_metacognitive_triage(isolated_db):
    """Verify routing decisions (Search, Tool, Calculate, Clarification, Abstain) based on metacognitive evaluation."""
    
    actions_to_test = ["SEARCH", "TOOL", "CALCULATE", "ASK_CLARIFICATION", "ABSTAIN"]
    
    for action in actions_to_test:
        def mock_verify_grounding(state):
            return {
                "grounded": False if action != "ANSWER" else True,
                "confidence": 0.4,
                "recommended_action": action,
                "new_search_query": None,
                "reason": f"Gate selected {action}"
            }
            
        with patch("backend.core.metacognition.MetacognitiveGate.verify_grounding", side_effect=mock_verify_grounding), \
             patch("backend.core.rbil.RBIL.process", return_value=None), \
             patch("backend.core.rbil.RBIL.classify_escalation_level", return_value=0), \
             patch("backend.agents.evaluator.guard_relevance_reply", side_effect=lambda q, r: r), \
             patch("backend.agents.evaluator.guard_interaction_reply", side_effect=lambda q, r: r), \
             patch("backend.core.model_router.ask_model") as mock_ask:
            mock_ask.return_value = "Mocked LLM reply for " + action
            
            result = run_graph("metacognition test query")
            
            assert result["metacognitive_action"] == action
            if action in ("ASK_CLARIFICATION", "ABSTAIN"):
                assert result["result"] == "Mocked LLM reply for " + action
            else:
                # Specialist nodes or council/planner should have been reached
                assert any("Personality Council" in log or "planner" in log for log in result["logs"])


def test_world_model_simulation(isolated_db):
    """Verify that WorldModel simulation executes prior to specialist tools/commands."""
    with patch("backend.core.metacognition.MetacognitiveGate.verify_grounding") as mock_meta, \
         patch("backend.core.model_router.ask_model") as mock_ask:
         
        mock_meta.return_value = {
            "grounded": True,
            "confidence": 0.9,
            "recommended_action": "TOOL",
            "new_search_query": None,
            "reason": "needs file edit tool"
        }
        
        # Setup ask_model mock:
        # First call is reasoning hypothesis
        # Second call is council debate
        # Third call is planning
        # Fourth call is world model simulator prediction
        def side_effect(prompt, role="general", system=None):
            if "World Model Simulator" in prompt:
                return json.dumps({
                    "predicted_success": 0.88,
                    "predicted_cost": 2.5,
                    "predicted_time": "150ms",
                    "confidence_interval": [0.80, 0.95],
                    "risk_score": 0.12
                })
            elif "Council of Perspectives" in prompt or "auditor" in prompt.lower():
                return json.dumps({
                    "decision": "APPROVE",
                    "confidence": 0.95,
                    "evidence_type": "reasoning",
                    "risks": [],
                    "benefits": [],
                    "rationale": "approved"
                })
            else:
                # Default response
                return "standard response"
                
        mock_ask.side_effect = side_effect
        
        # Running the graph
        result = run_graph("create a file called index.html")
        
        # Check that world model prediction is in state
        pred = result["world_model_prediction"]
        assert pred is not None
        assert pred["predicted_success"] == 0.88
        assert pred["predicted_cost"] == 2.5
        assert pred["predicted_time"] == "150ms"
        assert pred["confidence_interval"] == (0.80, 0.95)
        assert pred["risk_score"] == 0.12
        
        # Assert database contains the recorded prediction
        db_pred = WorldModel.get_prediction(pred["prediction_id"])
        assert db_pred is not None
        assert db_pred["action"].lower() == result["selected_agent"].lower()
        assert db_pred["predicted_success"] == 0.88


def test_source_tagged_context(isolated_db):
    """Verify recalled memory context elements carry source and confidence tags."""
    # Seed episodic memory, semantic context, and relationship notes to ensure recall formats them
    from backend.core.memory import memory
    from backend.core.episodic_memory import EpisodicMemory
    from backend.core.relationship_memory import RelationshipMemory
    
    # Mock MemoryRecall outputs directly to ensure deterministic content formatting
    mock_payload = {
        "episodic_history": [
            {"role": "user", "content": "hello world"}
        ],
        "semantic_context": [
            {"role": "user", "content": "cached semantic query", "confidence": 0.92, "source_type": "READ"}
        ],
        "cognitive_episodes": [
            {
                "event_summary": "file_write",
                "outcome_status": "SUCCESS",
                "derived_lesson": "always double check paths",
                "source_type": "DID",
                "composite_score": 0.96
            }
        ],
        "relationship_notes": {
            "identity": {"name": "Bala"},
            "trust_metrics": {"trust_score": 0.98}
        }
    }
    
    with patch("backend.core.memory_recall.MemoryRecall.recall", return_value=mock_payload):
        result = run_graph("test memory context formatting")
        ctx = result["memory_context"]
        
        assert "[source: READ, confidence: 1.0]" in ctx, "Episodic history must be source-tagged!"
        assert "[source: READ, confidence: 0.92]" in ctx, "Semantic memory must be source-tagged!"
        assert "[source: DID, confidence: 0.96]" in ctx, "Cognitive episode must be source-tagged!"
        assert "[source: INFERRED, confidence: 0.90]" in ctx, "Relationship name must be source-tagged!"
        assert "[source: INFERRED, confidence: 0.95]" in ctx, "Relationship trust metrics must be source-tagged!"

        # Assert Physical Reality Separation headers
        assert "### FACTS (Conversation History & Verified Facts)" in ctx
        assert "### EXECUTED ACTIONS (Actual System Executions)" in ctx
        assert "### SIMULATION MEMORY (Predictions & Hypothetical Scenarios)" in ctx
        assert "### BELIEF & USER PROFILE (Inferences & Preferences)" in ctx


def test_parallel_council_execution(isolated_db):
    """Verify that multiple perspectives in the council are run concurrently."""
    import time
    from backend.core.council_session import CouncilSession
    from backend.core.consensus_engine import AgentOutput, Decision, EvidenceType
    
    # Create some dummy perspectives
    from backend.core.council_session import CouncilPerspective
    p1 = CouncilPerspective(role="Rama", function="stability", domains=("planning",), base_weight=1.0)
    p2 = CouncilPerspective(role="Shiva", function="risk", domains=("architecture",), base_weight=1.0)
    p3 = CouncilPerspective(role="Kattappa", function="loyalty", domains=("user_impact",), base_weight=1.0)
    
    perspectives = [p1, p2, p3]
    
    # Mock _elicit_perspective as a plain function to avoid Mock class lock contention
    def mock_elicit(cls, perspective, **kwargs):
        time.sleep(0.1)
        output = AgentOutput(
            agent=perspective.role,
            decision=Decision.APPROVE,
            confidence=0.9,
            evidence=(EvidenceType.REASONING,),
            recommendations=(),
            source_id=f"council_{perspective.role.lower()}",
            rationale="dummy",
        )
        vote_rec = {
            "perspective": perspective.role,
            "vote": "APPROVE",
            "confidence": 0.9,
            "calibrated_confidence": 0.9,
            "calibration_factor": 1.0,
            "historical_judged": 0,
            "historical_correct": 0,
            "evidence_type": "reasoning",
            "rationale": "dummy",
            "risks": [],
            "benefits": [],
            "vote_weight": 1.0,
            "evidence_refs": [],
        }
        return output, vote_rec
        
    # Manual monkeypatch to avoid mock locking overhead
    original_elicit = CouncilSession._elicit_perspective
    CouncilSession._elicit_perspective = classmethod(mock_elicit)
    
    with patch.object(CouncilSession, "_run_auditor", return_value=([], [])):
        try:
            start_time = time.time()
            res = CouncilSession._run(
                question="test parallel run",
                question_type="general",
                context={},
                perspectives=perspectives,
                code_change=False,
                production=False,
                mode_profile="system_default"
            )
            elapsed = time.time() - start_time
            
            # Sequentially it would be at least 0.3s. Concurrently it should be ~0.1s.
            assert elapsed < 0.25, f"Deliberation was not parallelized! Elapsed: {elapsed:.3f}s"
        finally:
            CouncilSession._elicit_perspective = original_elicit


def test_low_confidence_memory_propagation(isolated_db):
    """Verify that a LOW memory confidence level forces the metacognitive gate to reject direct answers."""
    # We mock MemoryRecall.recall to simulate timeout / failure: returns LOW confidence
    mock_payload = {
        "episodic_history": [],
        "semantic_context": [],
        "cognitive_episodes": [],
        "relationship_notes": {},
        "memory_confidence_level": "LOW"
    }
    
    mock_attn = {
        "early_exit": None,
        "clean_message": "low confidence test query",
        "intent_type": "general",
        "focus_keywords": [],
        "complexity_level": 1,
        "requires_tools": False,
        "stakes_level": "low",
        "reversibility": "reversible",
        "required_confidence": 0.50,
        "path_selected": "FAST",
    }
    
    # We need mock_ask to return a valid Metacognitive Gate JSON response recommending RE_RETRIEVE or SEARCH
    def side_effect(prompt, role="general", system=None):
        if "Metacognitive Gate" in prompt:
            # Assert that the warning is indeed included in the prompt!
            assert "WARNING: Memory database query timed out or failed" in prompt
            return json.dumps({
                "grounded": False,
                "confidence": 0.2,
                "recommended_action": "RE_RETRIEVE",
                "new_search_query": "force retry",
                "reason": "memory confidence was low"
            })
        return "standard response"
    
    with patch("backend.core.attention.Attention.process", return_value=mock_attn), \
         patch("backend.core.memory_recall.MemoryRecall.recall", return_value=mock_payload), \
         patch("backend.core.metacognition.ask_model", side_effect=side_effect) as mock_ask_meta, \
         patch("backend.core.model_router.ask_model", side_effect=side_effect) as mock_ask_router:
        
        result = run_graph("low confidence test query")
        assert result["memory_confidence_level"] == "LOW"
        assert result["metacognitive_action"] == "RE_RETRIEVE"


def test_blackboard_workspace_writes(isolated_db):
    """Verify that intermediate cognitive nodes write facts, constraints, and outputs to the shared blackboard."""
    from backend.core.blackboard import EntryKind
    
    # mock all models
    def side_effect(prompt, role="general", system=None):
        if "reasoning subsystem" in prompt:
            return json.dumps({
                "hypothesis": "Hypothesis: execute the command safely",
                "missing_knowledge_gap": None,
                "search_query_for_gap": None
            })
        elif "Council of Perspectives" in prompt or "auditor" in prompt.lower():
            return json.dumps({
                "decision": "APPROVE",
                "confidence": 0.95,
                "evidence_type": "reasoning",
                "risks": [],
                "benefits": [],
                "rationale": "approved"
            })
        elif "World Model Simulator" in prompt:
            return json.dumps({
                "predicted_success": 0.95,
                "predicted_cost": 1.0,
                "predicted_time": "100ms",
                "confidence_interval": [0.90, 1.00],
                "risk_score": 0.05
            })
        elif "Metacognitive Gate" in prompt:
            return json.dumps({
                "grounded": True,
                "confidence": 0.9,
                "recommended_action": "TOOL",
                "new_search_query": None,
                "reason": "grounded"
            })
        return "default"
        
    with patch("backend.core.model_router.ask_model", side_effect=side_effect) as mock_ask_router, \
         patch("backend.core.metacognition.ask_model", side_effect=side_effect) as mock_ask_meta:
        
        # Safety review passes
        with patch("backend.core.safety_review.SafetyReview.review", return_value={"is_safe": True}):
            result = run_graph("do a tool action")
            
            board = result.get("blackboard")
            assert board is not None, "Blackboard workspace was not initialized!"
            
            # Inspect entries
            entries = board.entries()
            sources = [e.source for e in entries]
            
            # We expect reasoning, council_debate, world_model, safety_review to write to blackboard
            assert "reasoning" in sources
            assert "council_debate" in sources
            assert "world_model" in sources
            assert "safety_review" in sources
            
            # Verify kind of entries
            reasoning_entries = board.by_source("reasoning")
            assert len(reasoning_entries) > 0
            assert reasoning_entries[0].kind == EntryKind.AGENT_OUTPUT
            assert reasoning_entries[0].content["hypothesis"] == "Hypothesis: execute the command safely"
            
            safety_entries = board.by_source("safety_review")
            assert len(safety_entries) > 0
            assert safety_entries[0].kind == EntryKind.FACT
            assert safety_entries[0].content["is_safe"] is True


def test_recursive_cognition_loop(isolated_db):
    """Verify that if the reasoning node detects a gap, the graph loops back to memory and increments depth."""
    mock_attn = {
        "focus_keywords": ["database"],
        "intent_type": "database",
        "complexity_level": 1,
        "requires_tools": False,
        "clean_message": "test query",
        "early_exit": None,
        "stakes_level": "low",
        "reversibility": "reversible",
        "required_confidence": 0.50,
        "path_selected": "FAST"
    }

    # First call: returns a gap and query. Second call: returns no gap.
    reasoning_calls = 0
    def mock_ask_fn(prompt, role="general", system=None):
        nonlocal reasoning_calls
        if "reasoning subsystem" in prompt:
            reasoning_calls += 1
            if reasoning_calls == 1:
                return json.dumps({
                    "hypothesis": "First draft hypothesis",
                    "missing_knowledge_gap": "What is the secret key?",
                    "search_query_for_gap": "secret API key"
                })
            else:
                return json.dumps({
                    "hypothesis": "Refined hypothesis with secret key",
                    "missing_knowledge_gap": None,
                    "search_query_for_gap": None
                })
        elif "Metacognitive Gate" in prompt:
            return json.dumps({
                "grounded": True,
                "confidence": 0.95,
                "recommended_action": "ANSWER",
                "new_search_query": None,
                "reason": "fully resolved"
            })
        return "default"

    with patch("backend.core.attention.Attention.process", return_value=mock_attn), \
         patch("backend.core.model_router.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.metacognition.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.memory_recall.MemoryRecall.recall") as mock_recall:
         
        mock_recall.return_value = {
            "episodic_history": [],
            "semantic_context": [],
            "cognitive_episodes": [],
            "relationship_notes": {}
        }
        
        result = run_graph("test recursive loop query")
        
        # Verify loops and state
        assert mock_recall.call_count == 2
        assert result["reasoning_recursion_depth"] == 1
        assert result["memory_query"] == "secret API key"
        assert result["reasoning_hypothesis"] == "Refined hypothesis with secret key"
        assert any("detected knowledge gap" in log for log in result["logs"])


def test_recursive_cognition_depth_bound(isolated_db):
    """Verify that the recursive cognition loop bounds recursion to max 3 levels to avoid infinite loops."""
    mock_attn = {
        "focus_keywords": ["database"],
        "intent_type": "database",
        "complexity_level": 1,
        "requires_tools": False,
        "clean_message": "test query",
        "early_exit": None,
        "stakes_level": "low",
        "reversibility": "reversible",
        "required_confidence": 0.50,
        "path_selected": "FAST"
    }

    # Always returns a gap, which would loop forever without a bound
    def mock_ask_fn(prompt, role="general", system=None):
        if "reasoning subsystem" in prompt:
            return json.dumps({
                "hypothesis": "Hypothesis",
                "missing_knowledge_gap": "Persistent gap",
                "search_query_for_gap": "Persistent query"
            })
        elif "Metacognitive Gate" in prompt:
            return json.dumps({
                "grounded": True,
                "confidence": 0.95,
                "recommended_action": "ANSWER",
                "new_search_query": None,
                "reason": "resolved"
            })
        return "default"

    with patch("backend.core.attention.Attention.process", return_value=mock_attn), \
         patch("backend.core.model_router.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.metacognition.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.memory_recall.MemoryRecall.recall") as mock_recall:
         
        mock_recall.return_value = {
            "episodic_history": [],
            "semantic_context": [],
            "cognitive_episodes": [],
            "relationship_notes": {}
        }
        
        result = run_graph("test depth bound query")
        
        # Verify it terminated after depth 3
        assert mock_recall.call_count == 3
        assert result["reasoning_recursion_depth"] == 3
        assert result["reasoning_gaps"] == "Persistent gap"
        assert any("recursive recall (depth=3)" in log for log in result["logs"])


def test_recursive_cognition_context_accumulation(isolated_db):
    """Verify that successive memory recalls accumulate context block-by-block under explicit headers."""
    mock_attn = {
        "focus_keywords": ["database"],
        "intent_type": "database",
        "complexity_level": 1,
        "requires_tools": False,
        "clean_message": "test query",
        "early_exit": None,
        "stakes_level": "low",
        "reversibility": "reversible",
        "required_confidence": 0.50,
        "path_selected": "FAST"
    }

    reasoning_calls = 0
    def mock_ask_fn(prompt, role="general", system=None):
        nonlocal reasoning_calls
        if "reasoning subsystem" in prompt:
            reasoning_calls += 1
            if reasoning_calls == 1:
                return json.dumps({
                    "hypothesis": "Draft",
                    "missing_knowledge_gap": "need more",
                    "search_query_for_gap": "more context"
                })
            else:
                return json.dumps({
                    "hypothesis": "Final",
                    "missing_knowledge_gap": None,
                    "search_query_for_gap": None
                })
        elif "Metacognitive Gate" in prompt:
            return json.dumps({
                "grounded": True,
                "confidence": 0.95,
                "recommended_action": "ANSWER",
                "new_search_query": None,
                "reason": "resolved"
            })
        return "default"

    recall_calls = 0
    def mock_recall_fn(attention_frame, session_id, query=None):
        nonlocal recall_calls
        recall_calls += 1
        if recall_calls == 1:
            return {
                "episodic_history": [{"role": "user", "content": "initial context"}],
                "semantic_context": [],
                "cognitive_episodes": [],
                "relationship_notes": {}
            }
        else:
            return {
                "episodic_history": [{"role": "assistant", "content": "recursive context"}],
                "semantic_context": [],
                "cognitive_episodes": [],
                "relationship_notes": {}
            }

    with patch("backend.core.attention.Attention.process", return_value=mock_attn), \
         patch("backend.core.model_router.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.metacognition.ask_model", side_effect=mock_ask_fn), \
         patch("backend.core.memory_recall.MemoryRecall.recall", side_effect=mock_recall_fn):
         
        result = run_graph("test context accumulation query")
        
        context = result["memory_context"]
        assert context is not None
        assert "initial context" in context
        assert "=== RECURSIVE RECALL RESULT (Depth 1) ===" in context
        assert "recursive context" in context
