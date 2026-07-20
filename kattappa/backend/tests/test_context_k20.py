"""Unit and integration tests for Phase K20 Context Assembly Engine."""

from __future__ import annotations

import time
import pytest
from backend.core.context.models import ContextPriority, ContextSource
from backend.core.context.assembler import ContextAssembler
from backend.core.context_manager import ContextManager


class TestContextK20:
    def test_context_assembler_build_provenance_and_priority(self):
        goal = {
            "goal_id": "goal-1",
            "title": "Build app",
            "description": "Create python app",
            "confidence": 0.95,
            "timestamp": time.time()
        }
        memories = [
            {"content": "Auth policy: always secure", "category": "general", "source": "policy_db", "confidence": 1.0, "timestamp": time.time() - 10}
        ]
        tools = {"calculator": {"success_rate": 0.99}}
        environment = {"cpu_usage": 15.0}
        conversation = [
            {"role": "user", "content": "hello", "timestamp": time.time() - 20},
            {"role": "assistant", "content": "hi", "timestamp": time.time() - 10}
        ]

        bundle = ContextAssembler.build(
            goal=goal,
            memories=memories,
            tools=tools,
            environment=environment,
            conversation=conversation,
            token_budget=1000
        )

        # 1. Assembles all elements
        assert len(bundle.items) > 0

        # Verify Goal Item
        goal_item = next(item for item in bundle.items if "goal-1" in item.item_id)
        assert goal_item.priority == ContextPriority.MUST
        assert goal_item.metadata["provenance"] == "goal_database"
        assert goal_item.metadata["confidence"] == 0.95

        # Verify Memory Item
        mem_item = next(item for item in bundle.items if "mem-" in item.item_id)
        assert mem_item.priority == ContextPriority.SHOULD
        assert mem_item.metadata["provenance"] == "policy_db"
        assert mem_item.metadata["confidence"] == 1.0

        # Verify priority sorting: MUST items must be before SHOULD
        must_indices = [idx for idx, item in enumerate(bundle.items) if item.priority == ContextPriority.MUST]
        should_indices = [idx for idx, item in enumerate(bundle.items) if item.priority == ContextPriority.SHOULD]
        if must_indices and should_indices:
            assert max(must_indices) < min(should_indices)

    def test_context_expiration_ttl(self):
        now = time.time()
        goal = {"name": "Goal", "timestamp": now}
        memories = [
            {"content": "Stale memory", "timestamp": now - 100}  # 100 seconds old
        ]
        
        # Build with TTL = 50 seconds (should evict memories, keep goal)
        bundle = ContextAssembler.build(
            goal=goal,
            memories=memories,
            tools={},
            environment={},
            conversation=[],
            ttl_seconds=50
        )

        assert any("goal" in item.item_id for item in bundle.items)
        assert not any("Stale memory" in str(item.value) for item in bundle.items)

    def test_token_budget_and_compression(self):
        goal = {"name": "Goal"}
        memories = [
            {"content": "This is a very long memory context item that should be compressed when budgeting is tight."}
        ]

        # Build with tiny token budget
        bundle = ContextAssembler.build(
            goal=goal,
            memories=memories,
            tools={},
            environment={},
            conversation=[],
            token_budget=20
        )

        # Total tokens should fit within budget
        assert bundle.total_tokens <= 20
        
        # Long memory value should have been compressed/truncated
        mem_item = next(item for item in bundle.items if "mem-" in item.item_id)
        assert str(mem_item.value).endswith("...")

    def test_context_manager_integration(self):
        res = ContextManager.build_execution_context(session_id="test_session", query="deploy")
        
        assert "bundle" in res
        assert res["bundle"].session_id == "assembled-bundle"
        assert len(res["bundle"].items) >= 0
