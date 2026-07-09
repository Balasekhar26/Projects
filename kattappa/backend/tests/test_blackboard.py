"""Unit tests for Program 50.0: Cognitive Blackboard.

Verifies global pub/sub routing, wildcards, history filtering, and session-scoped workspaces.
"""
from __future__ import annotations

import pytest

from backend.core.blackboard import (
    CognitiveBlackboard,
    BlackboardPost,
    Blackboard,
    BlackboardEntry,
    SharedContext,
    EntryKind,
    BLACKBOARD,
)


@pytest.fixture(autouse=True)
def clean_blackboard():
    BLACKBOARD.clear()
    yield
    BLACKBOARD.clear()


# ── Cognitive Blackboard Tests ────────────────────────────────────────────────

class TestCognitiveBlackboard:
    def test_global_singleton_publish_and_receive(self):
        received_posts: list[BlackboardPost] = []
        
        # Subscribe to exact topic
        BLACKBOARD.subscribe("insight", received_posts.append)
        
        # Publish to the topic
        post = BLACKBOARD.publish(
            publisher="planner",
            topic="insight",
            payload={"key_claim": "found path"},
            confidence=0.95,
        )

        assert post.publisher == "planner"
        assert post.topic == "insight"
        assert post.payload["key_claim"] == "found path"
        assert post.confidence == 0.95
        
        # Verify subscriber callback trigger
        assert len(received_posts) == 1
        assert received_posts[0].post_id == post.post_id

    def test_wildcard_subscription(self):
        received_posts: list[BlackboardPost] = []
        
        # Subscribe to wildcard '*'
        BLACKBOARD.subscribe("*", received_posts.append)
        
        # Publish different topics
        BLACKBOARD.publish("agent_a", "observation", {"seen": "user"})
        BLACKBOARD.publish("agent_b", "hypothesis", {"guess": "failure"})
        
        assert len(received_posts) == 2
        assert {p.topic for p in received_posts} == {"observation", "hypothesis"}

    def test_history_queries(self):
        BLACKBOARD.publish("agent_a", "observation", {"i": 1})
        BLACKBOARD.publish("agent_b", "observation", {"i": 2})
        BLACKBOARD.publish("agent_b", "insight", {"key": "value"})

        # Query by topic
        obs_posts = BLACKBOARD.get_history(topic="observation")
        assert len(obs_posts) == 2
        assert all(p.topic == "observation" for p in obs_posts)

        # Query by publisher
        agent_b_posts = BLACKBOARD.get_history(publisher="agent_b")
        assert len(agent_b_posts) == 2
        assert all(p.publisher == "agent_b" for p in agent_b_posts)

    def test_post_lineage_referenced_ids(self):
        post_a = BLACKBOARD.publish("agent_a", "fact", {"val": 10})
        post_b = BLACKBOARD.publish(
            "agent_b",
            "insight",
            {"val": 20},
            referenced_ids=[post_a.post_id],
        )

        assert post_b.referenced_ids == (post_a.post_id,)


# ── Session Scoped Blackboard Tests ───────────────────────────────────────────

class TestSessionBlackboard:
    def test_session_scoped_workspace_crud(self):
        context = SharedContext(session_id="session_123", user_intent="test intent")
        workspace = Blackboard(context)
        
        # Add typed entries
        fact = workspace.add_fact("os_platform", "win32")
        assumption = workspace.add_assumption("api_online", True)
        constraint = workspace.add_constraint("timeout_seconds", 30)
        output = workspace.add_agent_output("result", "done")

        assert fact.kind == EntryKind.FACT
        assert assumption.kind == EntryKind.ASSUMPTION
        assert constraint.kind == EntryKind.CONSTRAINT
        assert output.kind == EntryKind.AGENT_OUTPUT

        # Read back entries
        assert workspace.get("os_platform").value == "win32"
        assert workspace.get("api_online").value is True
        
        # Filter entries by kind
        facts_list = workspace.entries(EntryKind.FACT)
        assert len(facts_list) == 1
        assert facts_list[0].key == "os_platform"

        # Clear workspace
        workspace.clear()
        assert len(workspace.entries()) == 0
