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
        return cls._add_compat_id(GoalMemory.update_goal_status(goal_id, GoalStatus.COMPLETED.value, "Goal completed successfully"))

    @classmethod
    def fail(cls, goal_id: str, reason: str = "Execution failed") -> Dict[str, Any]:
        """Marks goal as FAILED."""
        return cls._add_compat_id(GoalMemory.update_goal_status(goal_id, GoalStatus.FAILED.value, f"Goal failed: {reason}"))

    @classmethod
    def abandon(cls, goal_id: str) -> Dict[str, Any]:
        """Marks goal as CANCELLED."""
        return cls._add_compat_id(GoalMemory.update_goal_status(goal_id, GoalStatus.CANCELLED.value, "Goal cancelled/abandoned"))

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
    def handle_step_failure(cls, goal_id: str, step_error: str, max_retries: int = 3, backoff_factor: float = 1.5) -> Dict[str, Any]:
        """Handles a task step failure by checking retry count and performing backoff or triggering rollback."""
        import time
        goal = GoalMemory.get_goal(goal_id)
        if not goal:
            raise KeyError(f"No goal '{goal_id}'")

        meta = dict(goal.get("metadata") or {})
        retries = meta.get("retry_attempts", 0)
        
        if retries < max_retries:
            retries += 1
            meta["retry_attempts"] = retries
            # Calculate backoff delay
            delay = backoff_factor ** retries
            meta["next_retry_at"] = time.time() + delay
            
            # Update goal in GoalMemory
            GoalMemory.update_goal_metadata(goal_id, meta)
            
            # Transition status back to ACTIVE
            return cls._add_compat_id(GoalMemory.update_goal_status(
                goal_id, 
                GoalStatus.ACTIVE.value, 
                f"Retrying step (Attempt {retries}/{max_retries}) after {delay:.2f}s delay. Error: {step_error}"
            ))
        else:
            # Max retries exceeded -> Trigger Rollback if rollback details exist
            rollback_action = meta.get("rollback_action")
            reason = f"Max retries ({max_retries}) exceeded. Error: {step_error}"
            if rollback_action:
                reason += f" Triggered rollback: {rollback_action}"
                meta["rollback_executed"] = True
                GoalMemory.update_goal_metadata(goal_id, meta)
                
            return cls._add_compat_id(GoalMemory.update_goal_status(
                goal_id, 
                GoalStatus.FAILED.value, 
                reason
            ))

    @classmethod
    def reset(cls) -> None:
        """Resets the GoalMemory database. For testing purposes only."""
        GoalMemory.reset()
