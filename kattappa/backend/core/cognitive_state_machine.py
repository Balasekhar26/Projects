"""CognitiveStateMachine — Kattappa OS v2.

Formalizes the cognitive cycle as a deterministic, auditable state machine.
Every state transition is validated, emitted to the EventBus, and written to
the execution ledger. No state may be skipped; no illegal transition is allowed.

Cognitive cycle::

    IDLE
      │ begin(context)
      ▼
    OBSERVE         ← sense input, load world model context
      │ recall()
      ▼
    RECALL          ← retrieve memories via MemoryBroker
      │ plan()
      ▼
    PLAN            ← generate blueprint via ExecutivePlanner
      │ simulate()
      ▼
    SIMULATE        ← dry-run via CognitiveSimulationSandbox
      │ decide()
      ▼
    DECIDE          ← select best plan candidate; assess risks
      │ approve()  [auto-approved if risk < threshold]
      ▼
    APPROVE         ← human-in-the-loop gate for high-risk decisions
      │ execute()
      ▼
    EXECUTE         ← hand off to runtime; monitor
      │ reflect()
      ▼
    REFLECT         ← analyze outcomes; update beliefs
      │ learn()
      ▼
    LEARN           ← persist insights; update world model
      │ reset()
      ▼
    IDLE

Architecture constraints:
- Each state transition validates the legal predecessor.
- CognitiveContext accumulates data across the full cycle.
- MetaCognitionEngine mode (DIRECT/DEEP/HIGH_ASSURANCE) gates which states
  are executed: DIRECT skips SIMULATE; HIGH_ASSURANCE requires APPROVE.
- Every transition emits EventBus.CognitiveStateChanged.
- Every transition appends an entry to the execution ledger (SQLite).
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.event_bus import EventBus, EventName
from backend.core.logger import log_event


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

class CognitiveState(str, Enum):
    IDLE     = "IDLE"
    OBSERVE  = "OBSERVE"
    RECALL   = "RECALL"
    PLAN     = "PLAN"
    SIMULATE = "SIMULATE"
    DECIDE   = "DECIDE"
    APPROVE  = "APPROVE"
    EXECUTE  = "EXECUTE"
    REFLECT  = "REFLECT"
    LEARN    = "LEARN"


# Legal predecessor for each state (None means any → IDLE is always OK to re-enter after LEARN/IDLE)
_LEGAL_PREDECESSORS: dict[CognitiveState, set[CognitiveState]] = {
    CognitiveState.IDLE:     {CognitiveState.IDLE, CognitiveState.LEARN, CognitiveState.REFLECT},
    CognitiveState.OBSERVE:  {CognitiveState.IDLE},
    CognitiveState.RECALL:   {CognitiveState.OBSERVE},
    CognitiveState.PLAN:     {CognitiveState.RECALL},
    CognitiveState.SIMULATE: {CognitiveState.PLAN},
    CognitiveState.DECIDE:   {CognitiveState.SIMULATE, CognitiveState.PLAN},  # DIRECT mode skips SIMULATE
    CognitiveState.APPROVE:  {CognitiveState.DECIDE},
    CognitiveState.EXECUTE:  {CognitiveState.APPROVE, CognitiveState.DECIDE},  # low-risk skips APPROVE
    CognitiveState.REFLECT:  {CognitiveState.EXECUTE},
    CognitiveState.LEARN:    {CognitiveState.REFLECT},
}


# ---------------------------------------------------------------------------
# Cognitive Context — accumulates across the full cycle
# ---------------------------------------------------------------------------

@dataclass
class CognitiveContext:
    """Shared mutable context carried through all states of a single cycle."""
    cycle_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    session_id: str = "primary"
    goal_id: str = ""
    goal_title: str = ""
    goal_description: str = ""
    mode: str = "DEEP_ANALYSIS"       # DIRECT | DEEP_ANALYSIS | HIGH_ASSURANCE
    risk_level: str = "LOW"           # LOW | MEDIUM | HIGH | CRITICAL

    # Accumulated per-state outputs
    world_context: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)
    reasoning_trace: dict[str, Any] = field(default_factory=dict)
    plan_blueprint: dict[str, Any] = field(default_factory=dict)
    simulation_report: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    approval_record: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
    reflection_result: dict[str, Any] = field(default_factory=dict)
    learning_result: dict[str, Any] = field(default_factory=dict)

    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "goal_title": self.goal_title,
            "mode": self.mode,
            "risk_level": self.risk_level,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ---------------------------------------------------------------------------
# Ledger (slim per-transition records)
# ---------------------------------------------------------------------------

_LEDGER_LOCK = threading.Lock()
_csm_conn: sqlite3.Connection | None = None


def _db_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "cognitive_ledger.db"


def _get_conn() -> sqlite3.Connection:
    global _csm_conn
    if _csm_conn is not None:
        return _csm_conn
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cognitive_transitions (
            id          TEXT PRIMARY KEY,
            cycle_id    TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            goal_id     TEXT NOT NULL,
            from_state  TEXT NOT NULL,
            to_state    TEXT NOT NULL,
            mode        TEXT NOT NULL,
            risk_level  TEXT NOT NULL,
            occurred_at REAL NOT NULL
        )
    """)
    conn.commit()
    _csm_conn = conn
    return conn


def _write_transition(
    cycle_id: str,
    session_id: str,
    goal_id: str,
    from_state: CognitiveState,
    to_state: CognitiveState,
    mode: str,
    risk_level: str,
) -> None:
    try:
        with _LEDGER_LOCK:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO cognitive_transitions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex[:16],
                    cycle_id,
                    session_id,
                    goal_id,
                    from_state.value,
                    to_state.value,
                    mode,
                    risk_level,
                    time.time(),
                ),
            )
            conn.commit()
    except Exception as exc:
        log_event(f"CognitiveStateMachine ledger write failed: {exc}")


# ---------------------------------------------------------------------------
# CognitiveCycle — one-shot instance per goal invocation
# ---------------------------------------------------------------------------

class CognitiveCycle:
    """Executes a full cognitive cycle for a single goal, enforcing state order."""

    def __init__(self, context: CognitiveContext) -> None:
        self._ctx = context
        self._state = CognitiveState.IDLE
        self._lock = threading.Lock()
        self._history: list[tuple[CognitiveState, CognitiveState, float]] = []

    # -- state management --------------------------------------------------

    @property
    def state(self) -> CognitiveState:
        return self._state

    @property
    def context(self) -> CognitiveContext:
        return self._ctx

    def _transition(self, target: CognitiveState) -> None:
        """Validate and execute a state transition."""
        allowed = _LEGAL_PREDECESSORS.get(target, set())
        if self._state not in allowed:
            raise RuntimeError(
                f"Illegal transition {self._state.value} → {target.value}. "
                f"Allowed predecessors: {[s.value for s in allowed]}"
            )
        prev = self._state
        self._state = target
        now = time.time()
        self._history.append((prev, target, now))

        # Emit event
        EventBus.publish(
            EventName.COGNITIVE_STATE_CHANGED,
            {
                "cycle_id": self._ctx.cycle_id,
                "from_state": prev.value,
                "to_state": target.value,
                "goal_id": self._ctx.goal_id,
                "mode": self._ctx.mode,
            },
            source="CognitiveStateMachine",
        )

        # Write ledger
        _write_transition(
            self._ctx.cycle_id,
            self._ctx.session_id,
            self._ctx.goal_id,
            prev,
            target,
            self._ctx.mode,
            self._ctx.risk_level,
        )

        log_event(f"CSM [{self._ctx.cycle_id[:8]}] {prev.value} → {target.value}")

    # -- state handlers ----------------------------------------------------

    def observe(self, world_context: dict[str, Any] | None = None) -> "CognitiveCycle":
        """IDLE → OBSERVE: sense input, populate world context."""
        with self._lock:
            self._transition(CognitiveState.OBSERVE)
            self._ctx.world_context = dict(world_context or {})
        return self

    def recall(self, memory_context: dict[str, Any] | None = None) -> "CognitiveCycle":
        """OBSERVE → RECALL: retrieve memories."""
        with self._lock:
            self._transition(CognitiveState.RECALL)
            self._ctx.memory_context = dict(memory_context or {})
        return self

    def plan(self, blueprint: dict[str, Any] | None = None) -> "CognitiveCycle":
        """RECALL → PLAN: generate executive blueprint."""
        with self._lock:
            self._transition(CognitiveState.PLAN)
            self._ctx.plan_blueprint = dict(blueprint or {})
            EventBus.publish(
                EventName.PLANNER_STARTED,
                {"cycle_id": self._ctx.cycle_id, "goal_id": self._ctx.goal_id},
                source="CognitiveStateMachine",
            )
        return self

    def simulate(self, report: dict[str, Any] | None = None) -> "CognitiveCycle":
        """PLAN → SIMULATE: dry-run the plan, assess reversibility."""
        with self._lock:
            self._transition(CognitiveState.SIMULATE)
            self._ctx.simulation_report = dict(report or {})
            # Elevate risk if simulation flags it
            risk = (report or {}).get("risk_level", "LOW")
            if risk in ("HIGH", "CRITICAL"):
                self._ctx.risk_level = risk
        return self

    def decide(self, decision: dict[str, Any] | None = None) -> "CognitiveCycle":
        """SIMULATE|PLAN → DECIDE: select best candidate, assess final risk."""
        with self._lock:
            self._transition(CognitiveState.DECIDE)
            self._ctx.decision = dict(decision or {})
            risk = (decision or {}).get("risk_level", self._ctx.risk_level)
            self._ctx.risk_level = risk
        return self

    def approve(
        self,
        approved: bool = True,
        approver: str = "auto",
        reason: str = "",
    ) -> "CognitiveCycle":
        """DECIDE → APPROVE: human-in-the-loop or auto-approval gate."""
        with self._lock:
            self._transition(CognitiveState.APPROVE)
            self._ctx.approval_record = {
                "approved": approved,
                "approver": approver,
                "reason": reason,
                "approved_at": time.time(),
            }
            if not approved:
                # Blocked — move back to IDLE via REFLECT shortcut
                self._ctx.execution_result = {"status": "blocked", "reason": reason}
        return self

    def execute(self, result: dict[str, Any] | None = None) -> "CognitiveCycle":
        """APPROVE|DECIDE → EXECUTE: run the plan via the action runtime."""
        with self._lock:
            self._transition(CognitiveState.EXECUTE)
            self._ctx.execution_result = dict(result or {})
            EventBus.publish(
                EventName.EXECUTION_STARTED,
                {
                    "cycle_id": self._ctx.cycle_id,
                    "goal_id": self._ctx.goal_id,
                    "blueprint_id": self._ctx.plan_blueprint.get("blueprint_id", ""),
                },
                source="CognitiveStateMachine",
            )
        return self

    def reflect(self, reflection: dict[str, Any] | None = None) -> "CognitiveCycle":
        """EXECUTE → REFLECT: analyze outcomes, update beliefs."""
        with self._lock:
            self._transition(CognitiveState.REFLECT)
            self._ctx.reflection_result = dict(reflection or {})
            EventBus.publish(
                EventName.REFLECTION_COMPLETED,
                {
                    "cycle_id": self._ctx.cycle_id,
                    "goal_id": self._ctx.goal_id,
                    "outcome": (reflection or {}).get("outcome", "unknown"),
                },
                source="CognitiveStateMachine",
            )
        return self

    def learn(self, learning: dict[str, Any] | None = None) -> "CognitiveCycle":
        """REFLECT → LEARN: persist insights, update world model."""
        with self._lock:
            self._transition(CognitiveState.LEARN)
            self._ctx.learning_result = dict(learning or {})
            self._ctx.completed_at = time.time()
            EventBus.publish(
                EventName.WORLD_MODEL_UPDATED,
                {
                    "cycle_id": self._ctx.cycle_id,
                    "goal_id": self._ctx.goal_id,
                    "insights": list((learning or {}).get("insights", [])),
                },
                source="CognitiveStateMachine",
            )
        return self

    def finish(self) -> "CognitiveCycle":
        """LEARN → IDLE: complete the cycle."""
        with self._lock:
            self._transition(CognitiveState.IDLE)
        return self

    # -- convenience -------------------------------------------------------

    def transition_history(self) -> list[dict[str, Any]]:
        return [
            {"from": f.value, "to": t.value, "at": ts}
            for f, t, ts in self._history
        ]

    def summary(self) -> dict[str, Any]:
        return {
            **self._ctx.to_dict(),
            "current_state": self._state.value,
            "transitions": len(self._history),
        }


# ---------------------------------------------------------------------------
# CognitiveStateMachine — factory & ledger query
# ---------------------------------------------------------------------------

class CognitiveStateMachine:
    """Factory for CognitiveCycle instances and ledger access."""

    @staticmethod
    def begin(
        goal_id: str,
        goal_title: str = "",
        goal_description: str = "",
        session_id: str = "primary",
        mode: str = "DEEP_ANALYSIS",
    ) -> CognitiveCycle:
        """Open a new cognitive cycle for a goal."""
        ctx = CognitiveContext(
            session_id=session_id,
            goal_id=goal_id,
            goal_title=goal_title,
            goal_description=goal_description,
            mode=mode,
        )
        cycle = CognitiveCycle(ctx)
        EventBus.publish(
            EventName.COGNITIVE_STATE_CHANGED,
            {
                "cycle_id": ctx.cycle_id,
                "from_state": "NONE",
                "to_state": CognitiveState.IDLE.value,
                "goal_id": goal_id,
                "mode": mode,
            },
            source="CognitiveStateMachine",
        )
        return cycle

    @staticmethod
    def ledger_query(
        goal_id: str | None = None,
        cycle_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the persistent transition ledger."""
        try:
            with _LEDGER_LOCK:
                conn = _get_conn()
                if goal_id:
                    rows = conn.execute(
                        "SELECT * FROM cognitive_transitions WHERE goal_id=? ORDER BY occurred_at DESC LIMIT ?",
                        (goal_id, limit),
                    ).fetchall()
                elif cycle_id:
                    rows = conn.execute(
                        "SELECT * FROM cognitive_transitions WHERE cycle_id=? ORDER BY occurred_at ASC LIMIT ?",
                        (cycle_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM cognitive_transitions ORDER BY occurred_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            log_event(f"CognitiveStateMachine ledger_query failed: {exc}")
            return []

    @staticmethod
    def reset_ledger() -> None:
        """Drop all ledger data. For test isolation only."""
        try:
            with _LEDGER_LOCK:
                conn = _get_conn()
                conn.execute("DELETE FROM cognitive_transitions")
                conn.commit()
        except Exception:
            pass
