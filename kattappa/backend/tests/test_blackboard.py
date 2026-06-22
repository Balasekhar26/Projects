from __future__ import annotations

import threading

import pytest

from backend.core.blackboard import (
    AccessRights,
    Blackboard,
    DeltaOperation,
    EntryKind,
    ExecutionWorkspace,
    MemoryAssembler,
    MemoryDelta,
    MemoryKeeper,
    SharedContext,
    access_for,
)


def _open(assembler: MemoryAssembler, **kw) -> Blackboard:
    return ExecutionWorkspace.open("s1", assembler, **kw)


# ---------------------------------------------------------------------------
# Test 1: single retrieval
# ---------------------------------------------------------------------------

def test_single_retrieval_for_many_agents():
    assembler = MemoryAssembler()
    board = _open(assembler, user_intent="design")
    # Four agents all consume the same context object.
    for agent in ("Scientist", "Engineer", "Critic", "Planner"):
        ctx = board.context
        assert ctx is board.context  # same immutable object every time
    assert assembler.call_count == 1  # assembled exactly once


def test_assembler_uses_injected_providers_once():
    calls = {"working": 0}

    def working(_sid):
        calls["working"] += 1
        return {"active_task": "memory module"}

    assembler = MemoryAssembler(working_memory_provider=working)
    board = _open(assembler)
    assert board.context.working_memory["active_task"] == "memory module"
    assert calls["working"] == 1


# ---------------------------------------------------------------------------
# Test 2: append only
# ---------------------------------------------------------------------------

def test_blackboard_is_append_only():
    board = _open(MemoryAssembler())
    board.add_fact("Engineer", "uses SPI bus")
    board.add_fact("Scientist", "power budget is tight")
    assert len(board.entries()) == 2
    # No mutation API exists.
    for forbidden in ("overwrite", "update", "delete", "set", "__setitem__"):
        assert not hasattr(board, forbidden)


def test_entries_are_immutable():
    board = _open(MemoryAssembler())
    entry = board.add_fact("Engineer", "x")
    with pytest.raises(Exception):
        entry.content = "tampered"  # frozen dataclass


def test_entries_view_is_a_copy():
    board = _open(MemoryAssembler())
    board.add_fact("Engineer", "x")
    snapshot = board.entries()
    board.add_fact("Scientist", "y")
    assert len(snapshot) == 1  # earlier view not retroactively mutated
    assert len(board.entries()) == 2


# ---------------------------------------------------------------------------
# Test 3: delta proposal (agents cannot write memory)
# ---------------------------------------------------------------------------

def test_agent_without_rights_cannot_propose():
    board = _open(MemoryAssembler())
    delta = MemoryDelta("strategic", DeltaOperation.UPDATE, "milestone reached")
    with pytest.raises(PermissionError):
        board.submit_delta("Scientist", delta)  # read-only agent


def test_proposal_does_not_write_memory():
    committed = []
    keeper = MemoryKeeper(committer=lambda d: committed.append(d) or True)
    board = _open(MemoryAssembler())

    delta = MemoryDelta("strategic", DeltaOperation.UPDATE, "new project milestone reached", source="Engineer")
    proposal = board.submit_delta("Engineer", delta)
    assert proposal.status == "pending"
    # Submitting a delta must NOT have written anything.
    assert committed == []

    # Only the Memory Keeper commits, after validation.
    results = keeper.process_pending(board)
    assert len(results) == 1 and results[0].committed is True
    assert len(committed) == 1


def test_keeper_rejects_invalid_delta():
    keeper = MemoryKeeper(committer=lambda d: True, validator=lambda d: d.layer != "strategic")
    board = _open(MemoryAssembler())
    board.submit_delta("Planner", MemoryDelta("strategic", DeltaOperation.UPDATE, "x"))
    results = keeper.process_pending(board)
    assert results[0].committed is False
    assert "rejected" in results[0].reason


# ---------------------------------------------------------------------------
# Test 4: concurrent agents, no corruption
# ---------------------------------------------------------------------------

def test_concurrent_agents_no_corruption():
    board = _open(MemoryAssembler())

    def worker(i: int) -> None:
        for j in range(20):
            board.add_agent_output(f"agent{i}", {"i": i, "j": j})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    entries = board.entries()
    assert len(entries) == 5 * 20
    # Sequence numbers are unique and contiguous (no lost/overlapping writes).
    seqs = sorted(e.seq for e in entries)
    assert seqs == list(range(1, 101))
    # All five agents represented.
    assert {e.source for e in entries} == {f"agent{i}" for i in range(5)}


# ---------------------------------------------------------------------------
# Test 5: provenance preserved
# ---------------------------------------------------------------------------

def test_provenance_is_preserved():
    board = _open(MemoryAssembler())
    e1 = board.add_agent_output("Engineer", "use a star topology")
    e2 = board.add_agent_output("Critic", "single point of failure at the hub")
    assert e1.source == "Engineer"
    assert e2.source == "Critic"
    assert [e.source for e in board.by_source("Critic")] == ["Critic"]
    assert e1.kind is EntryKind.AGENT_OUTPUT


# ---------------------------------------------------------------------------
# Immutable shared context (Phase 2A)
# ---------------------------------------------------------------------------

def test_shared_context_is_immutable():
    ctx = SharedContext("s1", working_memory={"k": "v"}, strategic_memory=["g1"])
    with pytest.raises(Exception):
        ctx.user_intent = "changed"  # frozen
    with pytest.raises(TypeError):
        ctx.working_memory["k2"] = "v2"  # MappingProxyType is read-only
    assert ctx.strategic_memory == ("g1",)  # list coerced to tuple


def test_shared_context_to_dict_roundtrips_types():
    ctx = SharedContext("s1", guardrails=("g",), routing_decision={"intent": "architecture"})
    data = ctx.to_dict()
    assert data["guardrails"] == ["g"]
    assert data["routing_decision"] == {"intent": "architecture"}


# ---------------------------------------------------------------------------
# Access rules (Phase 2D)
# ---------------------------------------------------------------------------

def test_access_rules_match_spec():
    assert access_for("Engineer").delta_create is True
    assert access_for("Planner").delta_create is True
    assert access_for("Scientist").delta_create is False
    assert access_for("Critic").reflection_read is True
    assert access_for("Security").validator_read is True
    # Everyone can read the blackboard; unknown agents default to read-only.
    assert access_for("Scientist").blackboard_read is True
    assert access_for("Unknown") == AccessRights()


# ---------------------------------------------------------------------------
# Lifecycle: workspace is temporary cognition, destroyed after consensus
# ---------------------------------------------------------------------------

def test_workspace_destroy_blocks_further_use():
    board = _open(MemoryAssembler())
    board.add_fact("Engineer", "x")
    board.destroy()
    assert board.destroyed is True
    with pytest.raises(RuntimeError):
        board.add_fact("Engineer", "y")
    with pytest.raises(RuntimeError):
        board.submit_delta("Engineer", MemoryDelta("strategic", DeltaOperation.UPDATE, "x"))
