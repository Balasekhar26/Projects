"""
Goal Lifecycle Governor — Canonical state machine for Kattappa AIOS goals.

States:
    CREATED   → Initial state after goal registration.
    PLANNING  → Planner is decomposing the goal into subgoals / steps.
    READY     → All dependencies met; ready to execute.
    RUNNING   → Actively executing.
    BLOCKED   → Waiting on an external dependency or human input.
    FAILED    → Execution failed; may be eligible for retry.
    COMPLETED → Goal achieved.
    ARCHIVED  → Terminal tombstone state; immutable.

Valid transitions (adjacency matrix):
    CREATED   → PLANNING, READY
    PLANNING  → READY, FAILED, ARCHIVED
    READY     → RUNNING, ARCHIVED
    RUNNING   → COMPLETED, BLOCKED, FAILED
    BLOCKED   → READY, FAILED, ARCHIVED
    FAILED    → CREATED (retry), ARCHIVED
    COMPLETED → ARCHIVED
    ARCHIVED  → (none — terminal)
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Optional


class GoalStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


# Canonical transition graph
_VALID_TRANSITIONS: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.CREATED:   {GoalStatus.PLANNING, GoalStatus.READY},
    GoalStatus.PLANNING:  {GoalStatus.READY, GoalStatus.FAILED, GoalStatus.ARCHIVED},
    GoalStatus.READY:     {GoalStatus.RUNNING, GoalStatus.ARCHIVED},
    GoalStatus.RUNNING:   {GoalStatus.COMPLETED, GoalStatus.BLOCKED, GoalStatus.FAILED},
    GoalStatus.BLOCKED:   {GoalStatus.READY, GoalStatus.FAILED, GoalStatus.ARCHIVED},
    GoalStatus.FAILED:    {GoalStatus.CREATED, GoalStatus.ARCHIVED},
    GoalStatus.COMPLETED: {GoalStatus.ARCHIVED},
    GoalStatus.ARCHIVED:  set(),  # Terminal — no transitions allowed
}


class GoalTransitionError(Exception):
    """Raised when an illegal goal state transition is attempted."""


def can_transition(current: GoalStatus | str, target: GoalStatus | str) -> bool:
    """Returns True if a transition from `current` to `target` is legally permitted."""
    current = GoalStatus(current)
    target = GoalStatus(target)
    return target in _VALID_TRANSITIONS.get(current, set())


def validate_transition(current: GoalStatus | str, target: GoalStatus | str) -> None:
    """
    Validates that a transition from `current` to `target` is legal.
    Raises GoalTransitionError if the transition is not permitted.
    """
    current_s = GoalStatus(current)
    target_s = GoalStatus(target)
    if not can_transition(current_s, target_s):
        allowed = [s.value for s in _VALID_TRANSITIONS.get(current_s, set())]
        raise GoalTransitionError(
            f"Invalid goal transition: {current_s.value} → {target_s.value}. "
            f"Allowed targets from {current_s.value}: {allowed or ['(none — terminal)']}"
        )


class GoalLifecycleGovernor:
    """
    Manages goal state transitions, retry logic, and subgoal advancement.

    This class is the authoritative policy layer for goal lifecycle events.
    It is stateless with respect to persistence; it operates on goal dicts
    returned from a LedgerStore and delegates writes back to the store.
    """

    def __init__(self, store) -> None:
        """
        Args:
            store: A LedgerStore instance implementing goal CRUD methods.
        """
        self._store = store

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def create_goal(
        self,
        title: str,
        description: str | None = None,
        priority: int = 5,
        owner: str | None = None,
        owner_id: str | None = None,
        deadline_utc: float | None = None,
        confidence: float = 1.0,
        max_retries: int = 3,
        parent_goal_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        Creates and persists a new goal in CREATED status.

        Args:
            title: Human-readable goal title.
            description: Optional longer description.
            priority: Integer priority 1 (lowest) – 10 (highest).
            owner: Free-text owner label (e.g. username, agent name).
            owner_id: Optional ID of a registered principal.
            deadline_utc: POSIX timestamp of deadline, if any.
            confidence: Initial confidence estimate in [0.0, 1.0].
            max_retries: Maximum number of retry cycles before archiving.
            parent_goal_id: ID of parent goal for subgoal hierarchies.
            metadata: Arbitrary key-value metadata dict.

        Returns:
            The newly created goal dict.
        """
        if owner_id is not None:
            from backend.core.governance.identity_registry import IdentityRegistry
            registry = IdentityRegistry(self._store)
            registry.require(owner_id)

        now = time.time()
        goal = {
            "goal_id": f"GOAL-{uuid.uuid4().hex[:8].upper()}",
            "title": title,
            "description": description,
            "status": GoalStatus.CREATED.value,
            "priority": max(1, min(10, priority)),
            "owner": owner,
            "owner_id": owner_id,
            "deadline_utc": deadline_utc,
            "confidence": max(0.0, min(1.0, confidence)),
            "retry_count": 0,
            "max_retries": max_retries,
            "parent_goal_id": parent_goal_id,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }
        self._store.create_goal(goal)
        return goal

    def transition(self, goal_id: str, new_status: GoalStatus | str) -> dict:
        """
        Transitions a goal to a new status, validating the transition is legal.

        Args:
            goal_id: The ID of the goal to transition.
            new_status: The target status.

        Returns:
            The updated goal dict.

        Raises:
            KeyError: If goal_id does not exist.
            GoalTransitionError: If the transition is not permitted.
        """
        goal = self._store.get_goal(goal_id)
        if goal is None:
            raise KeyError(f"Goal '{goal_id}' not found.")

        validate_transition(goal["status"], new_status)

        new_status_str = GoalStatus(new_status).value
        self._store.update_goal_status(goal_id, new_status_str)
        goal["status"] = new_status_str
        goal["updated_at"] = time.time()
        return goal

    def retry_goal(self, goal_id: str) -> dict:
        """
        Attempts to retry a FAILED goal by resetting it to CREATED.

        The retry_count is incremented. If retry_count >= max_retries,
        the goal is ARCHIVED instead.

        Args:
            goal_id: The ID of the failed goal.

        Returns:
            The updated goal dict (either CREATED or ARCHIVED).

        Raises:
            GoalTransitionError: If the goal is not in FAILED status.
            KeyError: If the goal does not exist.
        """
        goal = self._store.get_goal(goal_id)
        if goal is None:
            raise KeyError(f"Goal '{goal_id}' not found.")

        if goal["status"] != GoalStatus.FAILED.value:
            raise GoalTransitionError(
                f"retry_goal called on a goal in status '{goal['status']}'. "
                f"Only FAILED goals can be retried."
            )

        new_retry_count = goal["retry_count"] + 1
        if new_retry_count >= goal["max_retries"]:
            self._store.update_goal_status(goal_id, GoalStatus.ARCHIVED.value, retry_count=new_retry_count)
            goal["status"] = GoalStatus.ARCHIVED.value
        else:
            self._store.update_goal_status(goal_id, GoalStatus.CREATED.value, retry_count=new_retry_count)
            goal["status"] = GoalStatus.CREATED.value

        goal["retry_count"] = new_retry_count
        goal["updated_at"] = time.time()
        return goal

    def advance_goal(self, goal_id: str) -> dict:
        """
        Inspects the current goal status and its subgoals to determine whether
        the goal can automatically advance to the next state.

        Advancement rules:
        - CREATED  → PLANNING (always, if no subgoals are defined yet)
        - PLANNING → READY    (if all subgoals are COMPLETED or READY)
        - BLOCKED  → READY    (if all blocking subgoals are COMPLETED)
        - RUNNING  → COMPLETED (if all subgoals are COMPLETED)

        Args:
            goal_id: The goal to inspect.

        Returns:
            The goal dict (possibly with updated status).
        """
        goal = self._store.get_goal(goal_id)
        if goal is None:
            raise KeyError(f"Goal '{goal_id}' not found.")

        subgoals = self._store.list_subgoals(goal_id)
        current = GoalStatus(goal["status"])

        next_status: Optional[GoalStatus] = None

        if current == GoalStatus.CREATED:
            next_status = GoalStatus.PLANNING

        elif current in (GoalStatus.PLANNING, GoalStatus.BLOCKED):
            if not subgoals:
                next_status = GoalStatus.READY
            else:
                all_done = all(
                    s["status"] in (GoalStatus.COMPLETED.value, GoalStatus.READY.value)
                    for s in subgoals
                )
                if all_done:
                    next_status = GoalStatus.READY

        elif current == GoalStatus.RUNNING:
            if subgoals and all(s["status"] == GoalStatus.COMPLETED.value for s in subgoals):
                next_status = GoalStatus.COMPLETED

        if next_status is not None and can_transition(current, next_status):
            return self.transition(goal_id, next_status)

        return goal
