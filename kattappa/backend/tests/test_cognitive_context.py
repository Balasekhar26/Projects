"""Unit tests for Program 33.0: Unified Cognitive State Engine.

Verifies ExecutionContext serialization, CognitiveContextManager thread-local properties,
and LifecycleHookManager callbacks propagation.
"""
from __future__ import annotations

import threading
import time

import pytest

from backend.core.context import (
    ExecutionContext,
    CognitiveContextManager,
    LifecycleHookManager,
)


# ── Execution Context Tests ───────────────────────────────────────────────────

class TestExecutionContext:
    def test_default_context_instantiation(self):
        ctx = ExecutionContext()
        assert len(ctx.goals) == 0
        assert len(ctx.constraints) == 0
        assert isinstance(ctx.beliefs, dict)
        assert isinstance(ctx.budget, dict)
        assert isinstance(ctx.permissions, dict)

    def test_context_deep_cloning(self):
        ctx = ExecutionContext(
            goals=["goal_1"],
            beliefs={"state": "A"},
            budget={"cost": 0.05},
        )
        
        cloned = ctx.clone()
        assert cloned.goals == ctx.goals
        assert cloned.beliefs == ctx.beliefs
        assert cloned.budget == ctx.budget
        
        # Mutate clone, original remains unmodified
        cloned.goals.append("goal_2")
        cloned.beliefs["state"] = "B"
        
        assert "goal_2" not in ctx.goals
        assert ctx.beliefs["state"] == "A"

    def test_to_dict_conversion(self):
        ctx = ExecutionContext(goals=["goal_1"], beliefs={"state": "A"})
        d = ctx.to_dict()
        
        assert "goals" in d
        assert "beliefs" in d
        assert d["goals"] == ["goal_1"]
        assert d["beliefs"]["state"] == "A"


# ── Cognitive Context Manager Tests ───────────────────────────────────────────

class TestCognitiveContextManager:
    def test_manager_singleton_and_thread_local(self):
        mgr = CognitiveContextManager()
        mgr.clear()

        # Thread local context instantiation
        ctx = mgr.get_current()
        ctx.goals.append("main_thread_goal")

        errors = []

        def other_thread_run():
            try:
                # Other thread should have a separate default context
                sub_ctx = mgr.get_current()
                assert "main_thread_goal" not in sub_ctx.goals
                sub_ctx.goals.append("sub_thread_goal")
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=other_thread_run)
        t.start()
        t.join()

        assert len(errors) == 0
        assert "sub_thread_goal" not in mgr.get_current().goals

    def test_set_current_validation(self):
        mgr = CognitiveContextManager()
        mgr.clear()

        with pytest.raises(TypeError):
            mgr.set_current("invalid_type")  # must raise TypeError


# ── Lifecycle Hook Manager Tests ──────────────────────────────────────────────

class TestLifecycleHookManager:
    def test_lifecycle_hooks_firing(self):
        hooks = LifecycleHookManager()
        hooks.clear_hooks()

        ctx = ExecutionContext()
        goal_events = []
        action_events = []
        change_events = []
        error_events = []

        # Register callbacks
        hooks.register_hook("on_goal_start", lambda c, gid: goal_events.append(gid))
        hooks.register_hook("on_action_dispatch", lambda c, name, args: action_events.append((name, args)))
        hooks.register_hook("on_context_change", lambda c, k, v: change_events.append((k, v)))
        hooks.register_hook("on_error_raised", lambda c, err: error_events.append(err))

        # Fire triggers
        hooks.fire_goal_start(ctx, "goal_123")
        hooks.fire_action_dispatch(ctx, "file_read", {"path": "/etc/hosts"})
        hooks.fire_context_change(ctx, "max_cost", 1.5)
        hooks.fire_error_raised(ctx, ValueError("Simulated error"))

        assert len(goal_events) == 1
        assert goal_events[0] == "goal_123"

        assert len(action_events) == 1
        assert action_events[0][0] == "file_read"
        assert action_events[0][1]["path"] == "/etc/hosts"

        assert len(change_events) == 1
        assert change_events[0][0] == "max_cost"
        assert change_events[0][1] == 1.5

        assert len(error_events) == 1
        assert isinstance(error_events[0], ValueError)
