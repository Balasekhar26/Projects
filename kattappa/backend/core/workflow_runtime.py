"""Workflow Runtime (Program 57.0).

Executes directed acyclic execution graphs produced by the SkillComposer.
Supports retry policies, per-node timeouts, checkpoint persistence, state
resumption, and full EventBus/AuditLedger integration.

Architecture:
    WorkflowRuntime
        │
        ├── WorkflowState  (per-run mutable execution state + checkpoint)
        │       ├── node states: PENDING / RUNNING / SUCCESS / FAILED / SKIPPED
        │       ├── outputs: Dict[node_name, Dict[str, Any]]
        │       └── retry counts
        │
        ├── WorkflowPolicy  (per-run retry / timeout configuration)
        │
        └── WorkflowRuntime.execute(composed_skill, policy, params)
                ├── Iterates execution_plan layers sequentially
                ├── Runs skills within each layer concurrently (ThreadPoolExecutor)
                ├── Applies per-node retry logic with exponential backoff
                ├── Falls back to fallback_plan on irrecoverable failure
                ├── Checkpoints state to SQLite after every layer
                └── Publishes WorkflowStarted / WorkflowLayerCompleted /
                    WorkflowCompleted / WorkflowFailed events to EventBus
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.core.config import runtime_data_root
from backend.core.event_bus import EventBus, EventName
from backend.core.skill_composer import ComposedSkill
from backend.core.skill_runtime import Skill


# ---------------------------------------------------------------------------
# Canonical new event names for Workflow Runtime
# ---------------------------------------------------------------------------

class WorkflowEventName:
    WORKFLOW_STARTED          = "WorkflowStarted"
    WORKFLOW_LAYER_COMPLETED  = "WorkflowLayerCompleted"
    WORKFLOW_NODE_STARTED     = "WorkflowNodeStarted"
    WORKFLOW_NODE_SUCCEEDED   = "WorkflowNodeSucceeded"
    WORKFLOW_NODE_FAILED      = "WorkflowNodeFailed"
    WORKFLOW_NODE_RETRYING    = "WorkflowNodeRetrying"
    WORKFLOW_NODE_SKIPPED     = "WorkflowNodeSkipped"
    WORKFLOW_COMPLETED        = "WorkflowCompleted"
    WORKFLOW_FAILED           = "WorkflowFailed"
    WORKFLOW_CHECKPOINT_SAVED = "WorkflowCheckpointSaved"


# ---------------------------------------------------------------------------
# Node execution state
# ---------------------------------------------------------------------------

class NodeState(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    SKIPPED  = "SKIPPED"


# ---------------------------------------------------------------------------
# Workflow execution policy
# ---------------------------------------------------------------------------

@dataclass
class WorkflowPolicy:
    """Controls retry, timeout, and concurrency behaviour for a workflow run."""

    # Maximum retries per skill node before failing the node
    max_retries: int = 2

    # Base delay (seconds) between retries — exponential backoff applied
    retry_base_delay: float = 0.5

    # Per-node timeout in seconds (wall-clock time for a single attempt)
    node_timeout: float = 30.0

    # Maximum number of concurrent threads for intra-layer parallelism
    max_concurrency: int = 4

    # Whether to continue execution skipping failed nodes that have no fallback
    continue_on_failure: bool = False


# ---------------------------------------------------------------------------
# Per-workflow mutable execution state
# ---------------------------------------------------------------------------

@dataclass
class WorkflowState:
    """Mutable execution state for a single workflow run, including checkpoint data."""

    workflow_id: str
    composed_skill_name: str
    node_states: Dict[str, NodeState] = field(default_factory=dict)
    node_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    node_errors: Dict[str, str] = field(default_factory=dict)
    retry_counts: Dict[str, int] = field(default_factory=dict)
    current_layer_index: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    final_status: str = "RUNNING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "composed_skill_name": self.composed_skill_name,
            "node_states": {k: v.value for k, v in self.node_states.items()},
            "node_outputs": self.node_outputs,
            "node_errors": self.node_errors,
            "retry_counts": self.retry_counts,
            "current_layer_index": self.current_layer_index,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "final_status": self.final_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowState":
        state = cls(
            workflow_id=data["workflow_id"],
            composed_skill_name=data["composed_skill_name"],
        )
        state.node_states = {k: NodeState(v) for k, v in data.get("node_states", {}).items()}
        state.node_outputs = data.get("node_outputs", {})
        state.node_errors = data.get("node_errors", {})
        state.retry_counts = data.get("retry_counts", {})
        state.current_layer_index = data.get("current_layer_index", 0)
        state.started_at = data.get("started_at", time.time())
        state.finished_at = data.get("finished_at")
        state.final_status = data.get("final_status", "RUNNING")
        return state


# ---------------------------------------------------------------------------
# Checkpoint store (SQLite)
# ---------------------------------------------------------------------------

_CHECKPOINT_DB_PATH = Path(runtime_data_root()) / "workflow_checkpoints.db"
_checkpoint_lock = threading.Lock()


def _checkpoint_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_CHECKPOINT_DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_checkpoints (
            workflow_id  TEXT PRIMARY KEY,
            state_json   TEXT NOT NULL,
            updated_at   REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _save_checkpoint(state: WorkflowState) -> None:
    with _checkpoint_lock:
        conn = _checkpoint_db()
        try:
            conn.execute(
                """
                INSERT INTO workflow_checkpoints (workflow_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at
                """,
                (state.workflow_id, json.dumps(state.to_dict()), time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def _load_checkpoint(workflow_id: str) -> Optional[WorkflowState]:
    with _checkpoint_lock:
        conn = _checkpoint_db()
        try:
            row = conn.execute(
                "SELECT state_json FROM workflow_checkpoints WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if row:
                return WorkflowState.from_dict(json.loads(row[0]))
            return None
        finally:
            conn.close()


def _delete_checkpoint(workflow_id: str) -> None:
    with _checkpoint_lock:
        conn = _checkpoint_db()
        try:
            conn.execute("DELETE FROM workflow_checkpoints WHERE workflow_id = ?", (workflow_id,))
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Workflow Runtime
# ---------------------------------------------------------------------------

class WorkflowRuntime:
    """Executes ComposedSkill DAGs with retry, timeout, checkpointing, and event integration.

    Usage:
        composed = SkillComposer.compose_skills(...)
        result = WorkflowRuntime.execute(
            composed_skill=composed,
            skill_factory=my_skill_factory_fn,
            params={"env": "production"},
            policy=WorkflowPolicy(max_retries=3),
        )
    """

    @classmethod
    def execute(
        cls,
        composed_skill: ComposedSkill,
        skill_factory: Callable[[str, Dict[str, Any]], Skill],
        params: Dict[str, Any] | None = None,
        policy: WorkflowPolicy | None = None,
        resume_workflow_id: str | None = None,
    ) -> Dict[str, Any]:
        """Execute a ComposedSkill DAG from start (or resume from checkpoint).

        Args:
            composed_skill:     A ComposedSkill object produced by SkillComposer.
            skill_factory:      Callable(skill_name, skill_def) -> Skill instance.
                                Gives the caller full control over Skill construction.
            params:             Global parameters passed to every skill node's execution.
            policy:             Retry and concurrency policy (defaults applied if None).
            resume_workflow_id: If provided, resumes execution from a persisted checkpoint.

        Returns:
            A result dict with keys:
                workflow_id, status, final_outputs, failed_nodes, elapsed_seconds.
        """
        policy = policy or WorkflowPolicy()
        params = params or {}

        # --- Resume or create fresh state ---
        if resume_workflow_id:
            state = _load_checkpoint(resume_workflow_id)
            if state is None:
                raise ValueError(f"No checkpoint found for workflow_id={resume_workflow_id!r}")
            workflow_id = resume_workflow_id
        else:
            workflow_id = uuid.uuid4().hex[:16]
            state = WorkflowState(
                workflow_id=workflow_id,
                composed_skill_name=composed_skill.name,
            )
            # Initialise all node states to PENDING
            for layer in composed_skill.execution_plan:
                for node_name in layer:
                    state.node_states[node_name] = NodeState.PENDING
                    state.retry_counts[node_name] = 0

        # Build lookup: name -> skill definition dict
        skills_by_name: Dict[str, Dict[str, Any]] = {
            s["name"]: s for s in composed_skill.constituent_skills
        }

        EventBus.publish(
            event_name=WorkflowEventName.WORKFLOW_STARTED,
            payload={
                "workflow_id": workflow_id,
                "composed_skill": composed_skill.name,
                "total_layers": len(composed_skill.execution_plan),
                "total_nodes": sum(len(l) for l in composed_skill.execution_plan),
            },
            source="WorkflowRuntime",
        )

        failed_nodes: List[str] = []
        final_outputs: Dict[str, Any] = {}

        # --- Layer-sequential execution ---
        for layer_idx, layer in enumerate(composed_skill.execution_plan):
            # Skip already-completed layers on resume
            if layer_idx < state.current_layer_index:
                continue

            state.current_layer_index = layer_idx

            layer_results = cls._execute_layer(
                layer=layer,
                state=state,
                skills_by_name=skills_by_name,
                skill_factory=skill_factory,
                fallback_plan=composed_skill.fallback_plan,
                params=params,
                policy=policy,
                workflow_id=workflow_id,
            )

            # Collect outputs and track failures
            for node_name, node_result in layer_results.items():
                if node_result["status"] == "success":
                    final_outputs[node_name] = node_result.get("outputs", {})
                    state.node_states[node_name] = NodeState.SUCCESS
                    state.node_outputs[node_name] = node_result.get("outputs", {})
                elif node_result["status"] == "skipped":
                    state.node_states[node_name] = NodeState.SKIPPED
                else:
                    failed_nodes.append(node_name)
                    state.node_states[node_name] = NodeState.FAILED
                    state.node_errors[node_name] = node_result.get("reason", "unknown error")

            # Checkpoint after every layer
            _save_checkpoint(state)
            EventBus.publish(
                event_name=WorkflowEventName.WORKFLOW_CHECKPOINT_SAVED,
                payload={"workflow_id": workflow_id, "layer_index": layer_idx},
                source="WorkflowRuntime",
            )

            EventBus.publish(
                event_name=WorkflowEventName.WORKFLOW_LAYER_COMPLETED,
                payload={
                    "workflow_id": workflow_id,
                    "layer_index": layer_idx,
                    "layer": layer,
                    "failed_nodes": [n for n in layer if state.node_states[n] == NodeState.FAILED],
                },
                source="WorkflowRuntime",
            )

            # Abort if there are failures and policy does not allow continuation
            if failed_nodes and not policy.continue_on_failure:
                break

        elapsed = time.time() - state.started_at
        state.finished_at = time.time()

        if failed_nodes and not policy.continue_on_failure:
            state.final_status = "FAILED"
            EventBus.publish(
                event_name=WorkflowEventName.WORKFLOW_FAILED,
                payload={
                    "workflow_id": workflow_id,
                    "failed_nodes": failed_nodes,
                    "elapsed_seconds": round(elapsed, 3),
                },
                source="WorkflowRuntime",
            )
        else:
            state.final_status = "COMPLETED"
            _delete_checkpoint(workflow_id)
            EventBus.publish(
                event_name=WorkflowEventName.WORKFLOW_COMPLETED,
                payload={
                    "workflow_id": workflow_id,
                    "elapsed_seconds": round(elapsed, 3),
                    "nodes_completed": len(final_outputs),
                },
                source="WorkflowRuntime",
            )

        return {
            "workflow_id": workflow_id,
            "status": state.final_status,
            "final_outputs": final_outputs,
            "failed_nodes": failed_nodes,
            "elapsed_seconds": round(elapsed, 3),
        }

    @classmethod
    def _execute_layer(
        cls,
        layer: List[str],
        state: WorkflowState,
        skills_by_name: Dict[str, Dict[str, Any]],
        skill_factory: Callable[[str, Dict[str, Any]], Skill],
        fallback_plan: Dict[str, str],
        params: Dict[str, Any],
        policy: WorkflowPolicy,
        workflow_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Execute all nodes in a single DAG layer concurrently with retry logic."""

        layer_results: Dict[str, Dict[str, Any]] = {}
        lock = threading.Lock()

        def _run_node(node_name: str) -> None:
            skill_def = skills_by_name.get(node_name, {})
            effective_name = node_name
            attempts = 0
            last_result: Dict[str, Any] = {}

            state.node_states[node_name] = NodeState.RUNNING
            EventBus.publish(
                event_name=WorkflowEventName.WORKFLOW_NODE_STARTED,
                payload={"workflow_id": workflow_id, "node": node_name},
                source="WorkflowRuntime",
            )

            # Retry loop
            while attempts <= policy.max_retries:
                try:
                    skill_instance = skill_factory(effective_name, skill_def)
                    start_t = time.time()
                    result = skill_instance.execute(params)
                    elapsed_node = time.time() - start_t

                    if elapsed_node > policy.node_timeout:
                        result = {
                            "status": "failed",
                            "reason": f"Node {effective_name!r} exceeded timeout of {policy.node_timeout}s",
                        }

                except Exception as exc:  # noqa: BLE001
                    result = {"status": "failed", "reason": str(exc)}

                last_result = result

                if result.get("status") == "success":
                    EventBus.publish(
                        event_name=WorkflowEventName.WORKFLOW_NODE_SUCCEEDED,
                        payload={"workflow_id": workflow_id, "node": node_name, "attempts": attempts + 1},
                        source="WorkflowRuntime",
                    )
                    break

                attempts += 1
                state.retry_counts[node_name] = attempts

                if attempts <= policy.max_retries:
                    backoff = policy.retry_base_delay * (2 ** (attempts - 1))
                    EventBus.publish(
                        event_name=WorkflowEventName.WORKFLOW_NODE_RETRYING,
                        payload={
                            "workflow_id": workflow_id,
                            "node": node_name,
                            "attempt": attempts,
                            "backoff_seconds": backoff,
                        },
                        source="WorkflowRuntime",
                    )
                    time.sleep(backoff)

            # If still failed after retries, try fallback
            if last_result.get("status") != "success" and node_name in fallback_plan:
                fallback_name = fallback_plan[node_name]
                fallback_def = skills_by_name.get(fallback_name, {})
                EventBus.publish(
                    event_name=WorkflowEventName.WORKFLOW_NODE_RETRYING,
                    payload={
                        "workflow_id": workflow_id,
                        "node": node_name,
                        "fallback": fallback_name,
                    },
                    source="WorkflowRuntime",
                )
                try:
                    fallback_skill = skill_factory(fallback_name, fallback_def)
                    last_result = fallback_skill.execute(params)
                    if last_result.get("status") == "success":
                        last_result["used_fallback"] = fallback_name
                except Exception as exc:  # noqa: BLE001
                    last_result = {"status": "failed", "reason": f"Fallback also failed: {exc}"}

            # Handle fully failed node
            if last_result.get("status") != "success":
                if policy.continue_on_failure:
                    last_result = {"status": "skipped", "reason": last_result.get("reason", "skipped after retries")}
                    EventBus.publish(
                        event_name=WorkflowEventName.WORKFLOW_NODE_SKIPPED,
                        payload={"workflow_id": workflow_id, "node": node_name},
                        source="WorkflowRuntime",
                    )
                else:
                    EventBus.publish(
                        event_name=WorkflowEventName.WORKFLOW_NODE_FAILED,
                        payload={
                            "workflow_id": workflow_id,
                            "node": node_name,
                            "reason": last_result.get("reason"),
                        },
                        source="WorkflowRuntime",
                    )

            with lock:
                layer_results[node_name] = last_result

        # Dispatch all nodes in the layer concurrently
        max_workers = min(policy.max_concurrency, len(layer))
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
            futures = {executor.submit(_run_node, node): node for node in layer}
            for future in as_completed(futures):
                # Surface unexpected thread exceptions (node function always catches internally)
                exc = future.exception()
                if exc is not None:
                    node_name = futures[future]
                    with lock:
                        layer_results[node_name] = {"status": "failed", "reason": str(exc)}

        return layer_results

    @classmethod
    def load_checkpoint(cls, workflow_id: str) -> Optional[WorkflowState]:
        """Load persisted workflow state from the checkpoint database."""
        return _load_checkpoint(workflow_id)

    @classmethod
    def list_checkpoints(cls) -> List[Dict[str, Any]]:
        """Return a list of all persisted workflow checkpoint summaries."""
        with _checkpoint_lock:
            conn = _checkpoint_db()
            try:
                rows = conn.execute(
                    "SELECT workflow_id, updated_at FROM workflow_checkpoints ORDER BY updated_at DESC"
                ).fetchall()
                return [{"workflow_id": r[0], "updated_at": r[1]} for r in rows]
            finally:
                conn.close()
