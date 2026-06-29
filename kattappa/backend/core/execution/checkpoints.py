"""Durable Checkpoint Manager (Program 5G-6).

Serializes session states and execution contexts to disk to support recovery after crashes.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, Optional

from backend.core.execution.execution_state import ExecutionContext, ExecutionSession, ExecutionState

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages disk serialization and hydration of active session states."""

    def __init__(self, checkpoint_dir: str = "checkpoints") -> None:
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def _get_path(self, session_id: str) -> str:
        return os.path.join(self.checkpoint_dir, f"{session_id}.json")

    def save_checkpoint(self, session: ExecutionSession, context: ExecutionContext) -> None:
        """Saves current execution snapshot variables, progress, and status to disk."""
        data = {
            "session_id": session.session_id,
            "plan_id": session.plan_id,
            "status": session.status.value,
            "progress": session.progress,
            "completed_nodes": list(session.completed_nodes),
            "failed_nodes": list(session.failed_nodes),
            "running_nodes": list(session.running_nodes),
            "retry_counts": session.retry_counts,
            "context": {
                "variables": context.variables,
                "outputs": context.outputs,
                "is_cancelled": context.is_cancelled,
            }
        }
        path = self._get_path(session.session_id)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug("Saved checkpoint to: %s", path)
        except Exception as exc:
            logger.error("Failed to write execution checkpoint: %s", str(exc))

    def load_checkpoint(self, session_id: str) -> Optional[tuple[ExecutionSession, ExecutionContext]]:
        """Loads and hydrants a previously saved execution snapshot context."""
        path = self._get_path(session_id)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)

            session = ExecutionSession(
                session_id=data["session_id"],
                plan_id=data["plan_id"],
                status=ExecutionState(data["status"]),
                progress=data["progress"],
                completed_nodes=set(data["completed_nodes"]),
                failed_nodes=set(data["failed_nodes"]),
                running_nodes=set(data["running_nodes"]),
                retry_counts=data["retry_counts"],
            )

            ctx_data = data["context"]
            context = ExecutionContext(
                variables=ctx_data["variables"],
                outputs=ctx_data["outputs"],
                is_cancelled=ctx_data.get("is_cancelled", False),
            )

            return session, context
        except Exception as exc:
            logger.error("Failed to load checkpoint file: %s", str(exc))
            return None

    def delete_checkpoint(self, session_id: str) -> None:
        """Cleans up checkpoint file after successful execution completes."""
        path = self._get_path(session_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as exc:
                logger.warning("Could not delete checkpoint file: %s", str(exc))
