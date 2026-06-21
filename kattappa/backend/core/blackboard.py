"""Blackboard System - the multi-agent Execution Workspace (Phase 2).

This is *temporary cognition*, not memory. One query opens a workspace, agents
read a single shared context and append their findings, the consensus engine
decides, and the workspace is destroyed. Nothing here persists.

    Memory Keeper -> Memory Assembler (ONE retrieval)
                          |
                          v
                   Shared Context (immutable)
                          |
                     Blackboard  <- agents append (provenance kept)
                          |
                   Delta Proposals -> Memory Keeper -> validate -> commit

Carried-forward constraints (from earlier reviews), all enforced here:

* **Single retrieval** - the Memory Assembler runs exactly once per workspace;
  every agent consumes the same context (no N x duplication).
* **Immutable Shared Context** - agents read it, never mutate it (no hidden
  state drift between agents).
* **Append-only Blackboard** - entries are immutable and provenance-stamped;
  there is no overwrite/update/delete API.
* **Delta proposals, never direct writes** - agents propose memory changes;
  only the Memory Keeper validates and commits them.
* **Tightened per-agent access** - read-only by default; only Engineer/Planner
  may create deltas.

This module never imports or modifies the memory system: the assembler's data
sources and the committer are injected, so the workspace is fully decoupled.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EntryKind(str, Enum):
    FACT = "fact"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"
    AGENT_OUTPUT = "agent_output"


class DeltaOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


# ---------------------------------------------------------------------------
# Per-agent access rules (Phase 2D)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccessRights:
    blackboard_read: bool = True
    delta_create: bool = False
    reflection_read: bool = False
    validator_read: bool = False


AGENT_ACCESS: dict[str, AccessRights] = {
    "Scientist": AccessRights(),                          # read only
    "Engineer": AccessRights(delta_create=True),
    "Critic": AccessRights(reflection_read=True),         # read only + reflection
    "Planner": AccessRights(delta_create=True),
    "Teacher": AccessRights(),
    "Poet": AccessRights(),
    "Security": AccessRights(validator_read=True),        # read only + validator results
    "Builder": AccessRights(),
}


def access_for(agent: str) -> AccessRights:
    """Access rights for an agent; unknown agents get read-only by default."""
    return AGENT_ACCESS.get(agent, AccessRights())


# ---------------------------------------------------------------------------
# Immutable shared context (Phase 2A)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SharedContext:
    session_id: str
    user_intent: str = ""
    active_project: str = ""
    working_memory: Mapping[str, Any] = field(default_factory=dict)
    strategic_memory: tuple[Any, ...] = ()
    relationship_memory: tuple[Any, ...] = ()
    guardrails: tuple[str, ...] = ()
    constraints: tuple[Any, ...] = ()
    routing_decision: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Freeze all collections so agents cannot mutate shared context.
        object.__setattr__(self, "working_memory", MappingProxyType(dict(self.working_memory)))
        object.__setattr__(self, "routing_decision", MappingProxyType(dict(self.routing_decision)))
        object.__setattr__(self, "strategic_memory", tuple(self.strategic_memory))
        object.__setattr__(self, "relationship_memory", tuple(self.relationship_memory))
        object.__setattr__(self, "guardrails", tuple(self.guardrails))
        object.__setattr__(self, "constraints", tuple(self.constraints))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_intent": self.user_intent,
            "active_project": self.active_project,
            "working_memory": dict(self.working_memory),
            "strategic_memory": list(self.strategic_memory),
            "relationship_memory": list(self.relationship_memory),
            "guardrails": list(self.guardrails),
            "constraints": list(self.constraints),
            "routing_decision": dict(self.routing_decision),
        }


# ---------------------------------------------------------------------------
# Blackboard entries & delta proposals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BlackboardEntry:
    seq: int
    kind: EntryKind
    source: str
    content: Any
    created_at: float
    id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind.value,
            "source": self.source,
            "content": self.content,
            "created_at": self.created_at,
            "id": self.id,
        }


@dataclass(frozen=True)
class MemoryDelta:
    layer: str
    operation: DeltaOperation
    reason: str
    source: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", DeltaOperation(self.operation))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "operation": self.operation.value,
            "reason": self.reason,
            "source": self.source,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class DeltaProposal:
    id: str
    source: str
    delta: MemoryDelta
    status: str = "pending"  # pending -> committed | rejected (tracked by MemoryKeeper)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "source": self.source, "delta": self.delta.to_dict(), "status": self.status}


@dataclass(frozen=True)
class CommitResult:
    delta: MemoryDelta
    committed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"delta": self.delta.to_dict(), "committed": self.committed, "reason": self.reason}


# ---------------------------------------------------------------------------
# Blackboard (append-only workspace store)
# ---------------------------------------------------------------------------

class Blackboard:
    """Append-only, provenance-tracked, thread-safe workspace.

    There is intentionally no ``overwrite``/``update``/``delete`` method:
    history (Engineer said X, Critic disagreed) must be preserved.
    """

    def __init__(self, context: SharedContext) -> None:
        self._context = context
        self._entries: list[BlackboardEntry] = []
        self._pending: list[DeltaProposal] = []
        self._seq = 0
        self._lock = threading.Lock()
        self._destroyed = False

    @property
    def context(self) -> SharedContext:
        """The single, immutable shared context (read-only for all agents)."""
        return self._context

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def _ensure_active(self) -> None:
        if self._destroyed:
            raise RuntimeError("Execution workspace has been destroyed")

    # -- append-only writes ------------------------------------------------
    def append(self, kind: EntryKind, source: str, content: Any) -> BlackboardEntry:
        with self._lock:
            self._ensure_active()
            self._seq += 1
            entry = BlackboardEntry(
                seq=self._seq,
                kind=kind,
                source=source,
                content=content,
                created_at=time.time(),
                id=uuid.uuid4().hex[:12],
            )
            self._entries.append(entry)
            return entry

    def add_fact(self, source: str, content: Any) -> BlackboardEntry:
        return self.append(EntryKind.FACT, source, content)

    def add_constraint(self, source: str, content: Any) -> BlackboardEntry:
        return self.append(EntryKind.CONSTRAINT, source, content)

    def add_assumption(self, source: str, content: Any) -> BlackboardEntry:
        return self.append(EntryKind.ASSUMPTION, source, content)

    def add_agent_output(self, source: str, content: Any) -> BlackboardEntry:
        return self.append(EntryKind.AGENT_OUTPUT, source, content)

    # -- reads -------------------------------------------------------------
    def entries(self, kind: EntryKind | None = None) -> tuple[BlackboardEntry, ...]:
        with self._lock:
            items = tuple(self._entries)
        if kind is not None:
            items = tuple(e for e in items if e.kind is kind)
        return items

    def by_source(self, source: str) -> tuple[BlackboardEntry, ...]:
        return tuple(e for e in self.entries() if e.source == source)

    # -- delta proposals (no direct memory writes) -------------------------
    def submit_delta(self, agent: str, delta: MemoryDelta) -> DeltaProposal:
        """An agent proposes a memory change. This does NOT write memory.

        Raises PermissionError if the agent lacks delta-create rights.
        """
        if not access_for(agent).delta_create:
            raise PermissionError(f"Agent {agent!r} may not create memory deltas")
        with self._lock:
            self._ensure_active()
            proposal = DeltaProposal(id=uuid.uuid4().hex[:12], source=agent, delta=delta)
            self._pending.append(proposal)
            return proposal

    def pending_deltas(self) -> tuple[DeltaProposal, ...]:
        with self._lock:
            return tuple(self._pending)

    # -- lifecycle ---------------------------------------------------------
    def destroy(self) -> None:
        """End of query: discard the workspace (temporary cognition only)."""
        with self._lock:
            self._destroyed = True
            self._entries = []
            self._pending = []

    def snapshot(self) -> dict[str, Any]:
        return {
            "context": self._context.to_dict(),
            "entries": [e.to_dict() for e in self.entries()],
            "pending_deltas": [p.to_dict() for p in self.pending_deltas()],
            "destroyed": self._destroyed,
        }


# ---------------------------------------------------------------------------
# Memory Assembler - the single retrieval point
# ---------------------------------------------------------------------------

class MemoryAssembler:
    """Builds the immutable SharedContext with ONE retrieval per workspace.

    Data sources are injected callables so this never imports the memory system.
    ``call_count`` lets the single-retrieval invariant be verified directly.
    """

    def __init__(
        self,
        working_memory_provider: Callable[[str], Mapping[str, Any]] | None = None,
        strategic_provider: Callable[[str], tuple[Any, ...]] | None = None,
        relationship_provider: Callable[[str], tuple[Any, ...]] | None = None,
    ) -> None:
        self._working = working_memory_provider or (lambda _sid: {})
        self._strategic = strategic_provider or (lambda _sid: ())
        self._relationship = relationship_provider or (lambda _sid: ())
        self.call_count = 0

    def assemble(
        self,
        session_id: str,
        *,
        user_intent: str = "",
        active_project: str = "",
        guardrails: tuple[str, ...] = (),
        constraints: tuple[Any, ...] = (),
        routing_decision: Mapping[str, Any] | None = None,
    ) -> SharedContext:
        self.call_count += 1
        return SharedContext(
            session_id=session_id,
            user_intent=user_intent,
            active_project=active_project,
            working_memory=self._working(session_id),
            strategic_memory=tuple(self._strategic(session_id)),
            relationship_memory=tuple(self._relationship(session_id)),
            guardrails=tuple(guardrails),
            constraints=tuple(constraints),
            routing_decision=dict(routing_decision or {}),
        )


# ---------------------------------------------------------------------------
# Memory Keeper - the only component that may commit deltas
# ---------------------------------------------------------------------------

class MemoryKeeper:
    """Validates and commits delta proposals. Agents never hold the committer."""

    def __init__(
        self,
        committer: Callable[[MemoryDelta], bool] | None = None,
        validator: Callable[[MemoryDelta], bool] | None = None,
    ) -> None:
        self._committer = committer
        self._validator = validator or (lambda _delta: True)

    def process_pending(self, board: Blackboard) -> list[CommitResult]:
        results: list[CommitResult] = []
        for proposal in board.pending_deltas():
            delta = proposal.delta
            if not self._validator(delta):
                results.append(CommitResult(delta, False, "rejected by validation"))
                continue
            if self._committer is None:
                results.append(CommitResult(delta, False, "validated; no committer configured"))
                continue
            committed = bool(self._committer(delta))
            results.append(
                CommitResult(delta, committed, "committed" if committed else "committer declined")
            )
        return results


# ---------------------------------------------------------------------------
# Execution Workspace - opens a board with a single retrieval
# ---------------------------------------------------------------------------

class ExecutionWorkspace:
    """Factory that guarantees one retrieval per query, then hands back a board."""

    @staticmethod
    def open(session_id: str, assembler: MemoryAssembler, **context_kwargs: Any) -> Blackboard:
        context = assembler.assemble(session_id, **context_kwargs)  # SINGLE retrieval
        return Blackboard(context)
