"""Tests for Phase K10.5: Cognitive Blackboard."""
from __future__ import annotations

import pytest
import time
from backend.core.blackboard import CognitiveBlackboard, BlackboardPost, BLACKBOARD


@pytest.fixture(autouse=True)
def clean_blackboard():
    BLACKBOARD.clear()
    yield
    BLACKBOARD.clear()


def test_blackboard_singleton():
    bb1 = CognitiveBlackboard()
    bb2 = CognitiveBlackboard()
    assert bb1 is bb2
    assert bb1 is BLACKBOARD


def test_blackboard_publish_and_history():
    post1 = BLACKBOARD.publish(
        publisher="test_agent",
        topic="hypothesis",
        payload={"claim": "Radar range is 50m"},
        confidence=0.9,
    )
    assert post1.post_id is not None
    assert post1.publisher == "test_agent"
    assert post1.topic == "hypothesis"
    assert post1.payload["claim"] == "Radar range is 50m"
    assert post1.confidence == 0.9

    history = BLACKBOARD.get_history()
    assert len(history) == 1
    assert history[0].post_id == post1.post_id


def test_blackboard_exact_subscription():
    received_posts = []

    def callback(post: BlackboardPost):
        received_posts.append(post)

    BLACKBOARD.subscribe("insight", callback)

    # Publish on non-matching topic
    BLACKBOARD.publish("agent_a", "hypothesis", {"claim": "A"})
    assert len(received_posts) == 0

    # Publish on matching topic
    post2 = BLACKBOARD.publish("agent_a", "insight", {"insight": "B"})
    assert len(received_posts) == 1
    assert received_posts[0].post_id == post2.post_id


def test_blackboard_wildcard_subscription():
    received_posts = []

    def callback(post: BlackboardPost):
        received_posts.append(post)

    BLACKBOARD.subscribe("*", callback)

    BLACKBOARD.publish("agent_a", "hypothesis", {"claim": "A"})
    BLACKBOARD.publish("agent_b", "insight", {"insight": "B"})

    assert len(received_posts) == 2


def test_blackboard_lineage_referencing():
    post1 = BLACKBOARD.publish("agent_a", "observation", {"data": "raw sensor output"})
    post2 = BLACKBOARD.publish(
        publisher="agent_b",
        topic="hypothesis",
        payload={"claim": "sensor indicates target present"},
        confidence=0.85,
        referenced_ids=[post1.post_id],
    )

    assert post2.referenced_ids == (post1.post_id,)
    assert post2.to_dict()["referenced_ids"] == [post1.post_id]


def test_blackboard_filtering():
    BLACKBOARD.publish("agent_a", "topic_1", {})
    BLACKBOARD.publish("agent_b", "topic_1", {})
    BLACKBOARD.publish("agent_a", "topic_2", {})

    assert len(BLACKBOARD.get_history(topic="topic_1")) == 2
    assert len(BLACKBOARD.get_history(publisher="agent_a")) == 2
    assert len(BLACKBOARD.get_history(topic="topic_1", publisher="agent_a")) == 1
