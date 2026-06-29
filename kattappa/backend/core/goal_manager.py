"""Goal Manager (Phase 4 / Step 8.1 transition).

Acts as the coordinator for managing V1 Goals and Milestones using SQLite GoalMemory database.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from backend.core.goal_memory import GoalMemory


class GoalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"
    CANCELLED = "CANCELLED"

    # Rich cognitive states:
    IDEA = "IDEA"
    CONSIDERING = "CONSIDERING"
    PLANNING = "PLANNING"
    WAITING = "WAITING"
    ABANDONED = "ABANDONED"
    DORMANT = "DORMANT"
    STALE_CONTEXT = "STALE_CONTEXT"
    STUCK = "STUCK"
    CONFLICTED = "CONFLICTED"

    # Compatibility aliases
    PENDING = "PROPOSED"
    DONE = "COMPLETED"
    ABANDONED_COMPAT = "CANCELLED"


class GoalManager:
    """Core interface wrapping SQLite GoalMemory database with Step 8.3 Human-Like Goal System features."""

    @classmethod
    def _add_compat_id(cls, goal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if goal is not None:
            goal = dict(goal)
            goal["id"] = goal["goal_id"]
        return goal

    @classmethod
    def _add_compat_id_list(cls, goals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [cls._add_compat_id(g) for g in goals if g is not None]

    @classmethod
    def add_goal(
        cls,
        title: str,
        description: Optional[str] = None,
        priority: str = "MEDIUM",
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None,
        owner: Optional[str] = None,
        importance: float = 5.0,
        urgency: float = 5.0,
        strategic_alignment: float = 5.0,
        resource_cost: float = 2.0,
        # Human-Like additions:
        owner_agent: Optional[str] = None,
        horizon_type: str = "SHORT_TERM",
        current_state: str = "PROPOSED",
        importance_score: float = 50.0,
        urgency_score: float = 50.0,
        estimated_value: float = 50.0,
        confidence_score: float = 100.0,
        energy_required: str = "MEDIUM",
        risk_profile: float = 10.0,
        attention_score: float = 1.0,
        decay_rate: float = 0.0,
        provenance: str = "STATED",
        original_goal_text: Optional[str] = None,
        definition_of_done: Optional[str] = None,
        ttl: Optional[float] = None,
        max_retries: int = 0,
        retry_count: int = 0,
        last_attempt_at: Optional[float] = None,
        backoff_delay_sec: float = 0.0,
        workspace_snapshot_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a goal, sets optional parent/dependencies, and persists it with advanced cognitive attributes."""
        if not title or not title.strip():
            raise ValueError("Goal title cannot be empty or only whitespace.")

        metadata = {}
        if parent_id:
            metadata["parent_id"] = parent_id

        # Insert goal in SQLite database
        goal = GoalMemory.create_goal(
            title=title.strip(),
            description=description,
            priority=priority,
            target_date=target_date,
            success_criteria=success_criteria,
            owner=owner,
            metadata=metadata,
            importance=importance,
            urgency=urgency,
            strategic_alignment=strategic_alignment,
            resource_cost=resource_cost,
            parent_goal_id=parent_id,
            owner_agent=owner_agent,
            horizon_type=horizon_type,
            current_state=current_state,
            importance_score=importance_score,
            urgency_score=urgency_score,
            estimated_value=estimated_value,
            confidence_score=confidence_score,
            energy_required=energy_required,
            risk_profile=risk_profile,
            attention_score=attention_score,
            decay_rate=decay_rate,
            provenance=provenance,
            original_goal_text=original_goal_text,
            definition_of_done=definition_of_done,
            ttl=ttl,
            max_retries=max_retries,
            retry_count=retry_count,
            last_attempt_at=last_attempt_at,
            backoff_delay_sec=backoff_delay_sec,
            workspace_snapshot_json=workspace_snapshot_json,
        )
        
        # Add dependencies
        if depends_on:
            for dep in depends_on:
                # Validate dependency exists
                dep_goal = GoalMemory.get_goal(dep)
                if not dep_goal:
                    raise ValueError(f"Dependency goal '{dep}' does not exist.")
                GoalMemory.add_dependency(goal["goal_id"], dep)
                
        return cls._add_compat_id(GoalMemory.get_goal(goal["goal_id"]))

    @classmethod
    def add_milestones(cls, goal_id: str, milestones_list: List[Dict[str, Any]]) -> None:
        """Decomposes a goal into structured milestones."""
        GoalMemory.add_milestones(goal_id, milestones_list)

    @classmethod
    def start(cls, goal_id: str) -> Dict[str, Any]:
        """Starts goal execution loop (transitions state to ACTIVE)."""
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"No goal '{goal_id}'")

        # Provenance protection: INFERRED/PROPOSED goals cannot drive execution directly
        prov = goal.get("provenance")
        if prov in {"INFERRED", "PROPOSED"}:
            raise ValueError(f"Cannot execute {prov} goal directly. Promotion requires user approval/reaffirmation.")

        # Validate against absolute safety constraints prior to execution
        violation = GoalMemory.validate_against_absolute_policies(goal["title"], goal.get("description"))
        if violation:
            GoalMemory.update_goal_status(goal_id, "ABANDONED", f"Violates absolute safety policy: {violation}")
            raise ValueError(f"Execution blocked: Goal violates safety policy {violation}.")

        # Check dependencies
        unmet_dependencies = []
        for dep_id in goal.get("dependencies", []):
            dep = GoalMemory.get_goal(dep_id)
            if dep and dep["status"] not in {GoalStatus.COMPLETED.value, "COMPLETED"}:
                unmet_dependencies.append(dep_id)

        status = GoalStatus.BLOCKED.value if unmet_dependencies else GoalStatus.ACTIVE.value
        reason = f"Activated goal. Unmet dependencies: {unmet_dependencies}" if unmet_dependencies else "Activated goal"
        return cls._add_compat_id(GoalMemory.update_goal_status(goal_id, status, reason))

    @classmethod
    def complete(
        cls,
        goal_id: str,
        evidence: Optional[Dict[str, Any]] = None,
        validator: Optional[str] = None,
        user_confirmed: bool = False
    ) -> Dict[str, Any]:
        """Marks goal as COMPLETED, checking optional verification evidence and validating cognitive goals."""
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"No goal '{goal_id}'")

        is_cognitive = goal.get("metadata", {}).get("cognitive", False)
        if is_cognitive:
            if not validator and not user_confirmed:
                raise ValueError("Completion validation failed: Cognitive goals require an independent validator or user confirmation.")

            # Log validation event
            conn = GoalMemory._get_sqlite_conn()
            try:
                event_payload = {
                    "validator": validator or "User Confirmation",
                    "user_confirmed": user_confirmed,
                    "evidence": evidence or {}
                }
                GoalMemory._log_event_conn(conn, goal_id, "GOAL_VALIDATED", event_payload)
            finally:
                conn.close()

        # Log evidence details if supplied
        if evidence:
            GoalMemory._log_event_conn(GoalMemory._get_sqlite_conn(), goal_id, "COMPLETION_EVIDENCE_SUBMITTED", evidence)

        res = GoalMemory.update_goal_status(goal_id, GoalStatus.COMPLETED.value, "Goal completed successfully")

        # Log event to execution ledger
        from backend.core.cos.kernel import KERNEL
        from backend.core.ledger.models.event import LedgerEvent
        from backend.core.ledger.models.enums import EventType
        import time
        import uuid
        try:
            event = LedgerEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                parent_event_ids=[],
                goal_id=goal_id,
                session_id=goal_id,
                correlation_id=goal_id,
                timestamp_utc=time.time(),
                actor="system",
                subsystem="goal_manager",
                event_type=EventType.EXECUTION_COMPLETED,
                payload={"goal_id": goal_id, "evidence": evidence or {}},
            )
            KERNEL.ledger.append(event)
        except Exception:
            pass

        # Auto-unblock downstream dependencies
        all_goals = GoalMemory.list_goals()
        for g in all_goals:
            if g["status"] == GoalStatus.BLOCKED.value or g["current_state"] == "BLOCKED":
                # Check if all dependencies are now met
                unmet = False
                for dep_id in g.get("dependencies", []):
                    if dep_id == goal_id:
                        continue
                    dep = GoalMemory.get_goal(dep_id)
                    if dep and dep["status"] not in {GoalStatus.COMPLETED.value, "COMPLETED"}:
                        unmet = True
                        break
                if not unmet:
                    # Unblock and activate!
                    GoalMemory.update_goal_status(g["goal_id"], GoalStatus.ACTIVE.value, f"Unblocked by completion of {goal_id}")

        return cls._add_compat_id(res)

    @classmethod
    def fail(cls, goal_id: str, reason: str = "Execution failed") -> Dict[str, Any]:
        """Marks goal as FAILED or schedules retry if retries are not exhausted."""
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"No goal '{goal_id}'")

        max_ret = goal.get("max_retries", 0) or 0
        curr_ret = goal.get("retry_count", 0) or 0

        from backend.core.cos.kernel import KERNEL
        from backend.core.ledger.models.event import LedgerEvent
        from backend.core.ledger.models.enums import EventType
        import time
        import uuid

        if curr_ret < max_ret:
            # Increment retry count, update delay, transition back to proposed/waiting
            new_ret = curr_ret + 1
            delay = float(2 ** new_ret)
            GoalMemory.update_goal_scheduler_fields(
                goal_id,
                retry_count=new_ret,
                last_attempt_at=time.time(),
                backoff_delay_sec=delay
            )
            res = GoalMemory.update_goal_status(
                goal_id,
                GoalStatus.WAITING.value,
                f"Attempt {new_ret} failed, retrying after {delay}s backoff. Reason: {reason}"
            )
            try:
                event = LedgerEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    parent_event_ids=[],
                    goal_id=goal_id,
                    session_id=goal_id,
                    correlation_id=goal_id,
                    timestamp_utc=time.time(),
                    actor="system",
                    subsystem="goal_manager",
                    event_type=EventType.TOOL_FAILED,
                    payload={"goal_id": goal_id, "retry_count": new_ret, "backoff": delay, "reason": reason},
                )
                KERNEL.ledger.append(event)
            except Exception:
                pass
            return cls._add_compat_id(res)
        else:
            res = GoalMemory.update_goal_status(goal_id, GoalStatus.FAILED.value, f"Goal failed: {reason}")
            try:
                event = LedgerEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    parent_event_ids=[],
                    goal_id=goal_id,
                    session_id=goal_id,
                    correlation_id=goal_id,
                    timestamp_utc=time.time(),
                    actor="system",
                    subsystem="goal_manager",
                    event_type=EventType.EXECUTION_CANCELLED,
                    payload={"goal_id": goal_id, "reason": f"Retries exhausted. {reason}"},
                )
                KERNEL.ledger.append(event)
            except Exception:
                pass
            return cls._add_compat_id(res)

    @classmethod
    def abandon(cls, goal_id: str) -> Dict[str, Any]:
        """Marks goal as CANCELLED."""
        res = GoalMemory.update_goal_status(goal_id, GoalStatus.CANCELLED.value, "Goal cancelled/abandoned")
        from backend.core.cos.kernel import KERNEL
        from backend.core.ledger.models.event import LedgerEvent
        from backend.core.ledger.models.enums import EventType
        import time
        import uuid
        try:
            event = LedgerEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                parent_event_ids=[],
                goal_id=goal_id,
                session_id=goal_id,
                correlation_id=goal_id,
                timestamp_utc=time.time(),
                actor="system",
                subsystem="goal_manager",
                event_type=EventType.EXECUTION_CANCELLED,
                payload={"goal_id": goal_id, "reason": "Goal cancelled/abandoned by user"},
            )
            KERNEL.ledger.append(event)
        except Exception:
            pass
        return cls._add_compat_id(res)

    @classmethod
    def suspend(cls, goal_id: str, reason: str = "Suspended") -> Dict[str, Any]:
        """Suspends goal execution. Serializes active workspace to snapshot and sets status to WAITING."""
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"No goal '{goal_id}'")

        from backend.core.executive_workspace import WORKSPACE
        ws_data = WORKSPACE.to_dict()
        import json
        ws_json = json.dumps(ws_data)

        GoalMemory.update_goal_scheduler_fields(goal_id, workspace_snapshot_json=ws_json)
        res = GoalMemory.update_goal_status(goal_id, GoalStatus.WAITING.value, reason)

        from backend.core.cos.kernel import KERNEL
        from backend.core.ledger.models.event import LedgerEvent
        from backend.core.ledger.models.enums import EventType
        import time
        import uuid
        try:
            event = LedgerEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                parent_event_ids=[],
                goal_id=goal_id,
                session_id=goal_id,
                correlation_id=goal_id,
                timestamp_utc=time.time(),
                actor="system",
                subsystem="goal_manager",
                event_type=EventType.INTERRUPT_RAISED,
                payload={"goal_id": goal_id, "reason": reason},
            )
            KERNEL.ledger.append(event)
        except Exception:
            pass

        return cls._add_compat_id(res)

    @classmethod
    def resume(cls, goal_id: str, reason: str = "Resumed") -> Dict[str, Any]:
        """Resumes suspended goal execution. Restores active workspace from snapshot and sets status to ACTIVE."""
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"No goal '{goal_id}'")

        ws_snapshot = goal.get("workspace_snapshot_json")
        if ws_snapshot:
            import json
            from backend.core.executive_workspace import WORKSPACE
            try:
                ws_data = json.loads(ws_snapshot)
                WORKSPACE.from_dict(ws_data)
            except Exception:
                pass

        res = GoalMemory.update_goal_status(goal_id, GoalStatus.ACTIVE.value, reason)

        from backend.core.cos.kernel import KERNEL
        from backend.core.ledger.models.event import LedgerEvent
        from backend.core.ledger.models.enums import EventType
        import time
        import uuid
        try:
            event = LedgerEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                parent_event_ids=[],
                goal_id=goal_id,
                session_id=goal_id,
                correlation_id=goal_id,
                timestamp_utc=time.time(),
                actor="system",
                subsystem="goal_manager",
                event_type=EventType.INTERRUPT_HANDLED,
                payload={"goal_id": goal_id, "reason": reason},
            )
            KERNEL.ledger.append(event)
        except Exception:
            pass

        return cls._add_compat_id(res)

    @classmethod
    def update_goal_scheduler_fields(
        cls,
        goal_id: str,
        retry_count: Optional[int] = None,
        last_attempt_at: Optional[float] = None,
        backoff_delay_sec: Optional[float] = None,
        workspace_snapshot_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates scheduler state fields on a goal."""
        return cls._add_compat_id(GoalMemory.update_goal_scheduler_fields(
            goal_id,
            retry_count=retry_count,
            last_attempt_at=last_attempt_at,
            backoff_delay_sec=backoff_delay_sec,
            workspace_snapshot_json=workspace_snapshot_json,
        ))

    @classmethod
    def reaffirm(cls, goal_id: str) -> Dict[str, Any]:
        """Reaffirms a goal to reset its TTL expiration timer."""
        return cls._add_compat_id(GoalMemory.reaffirm_goal(goal_id))

    @classmethod
    def get(cls, goal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves goal details."""
        return cls._add_compat_id(GoalMemory.get_goal(goal_id))

    @classmethod
    def list_goals(cls, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all goals in the system, sorted by priority_score descending."""
        goals = GoalMemory.list_goals(status)
        sorted_goals = sorted(goals, key=lambda g: g.get("priority_score", 0.0), reverse=True)
        return cls._add_compat_id_list(sorted_goals)

    @classmethod
    def subgoals(cls, parent_id: str) -> List[Dict[str, Any]]:
        """Lists all child goals of a specific parent goal."""
        all_goals = GoalMemory.list_goals()
        sub = []
        for g in all_goals:
            p_id = g.get("metadata", {}).get("parent_id") or g.get("parent_goal_id")
            if p_id == parent_id:
                sub.append(g)
        return cls._add_compat_id_list(sub)

    @classmethod
    def ready_goals(cls) -> List[Dict[str, Any]]:
        """Returns all proposed/planning goals with satisfied dependencies."""
        goals = cls.list_goals()
        ready = []
        for g in goals:
            if g["status"] in {GoalStatus.PROPOSED.value, "PROPOSED", "IDEA", "PLANNING"}:
                unmet = False
                for dep_id in g.get("dependencies", []):
                    dep = cls.get(dep_id)
                    if dep and dep["status"] not in {GoalStatus.COMPLETED.value, "COMPLETED"}:
                        unmet = True
                        break
                if not unmet:
                    ready.append(g)
        return ready

    @classmethod
    def progress(cls, goal_id: str) -> float:
        """Returns the derived progress percentage (0.0 to 1.0) of a goal."""
        goal = GoalMemory.get_goal(goal_id)
        return goal["progress"] if goal else 0.0

    @classmethod
    def status(cls) -> Dict[str, Any]:
        """Returns aggregate stats of all goals."""
        goals = cls.list_goals()
        
        # Collect dynamic status categories including rich states
        all_states = set(s.value for s in GoalStatus)
        by_status = {st: 0 for st in all_states}
        for g in goals:
            by_status[g["status"]] = by_status.get(g["status"], 0) + 1

        roots = [g for g in goals if not g.get("metadata", {}).get("parent_id") and not g.get("parent_goal_id")]
        ready_list = cls.ready_goals()

        return {
            "total_goals": len(goals),
            "by_status": by_status,
            "roots": [{"id": g["goal_id"], "title": g["title"], "progress": g["progress"]} for g in roots],
            "ready": [g["goal_id"] for g in ready_list],
        }

    @classmethod
    def reset(cls) -> None:
        """Resets the GoalMemory database. For testing purposes only."""
        GoalMemory.reset()
