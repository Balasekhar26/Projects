"""Mission Interrupt Handler (Program 24.0).

Handles active mission execution crashes, reboots, or timeouts, permitting resumption from checkpoints.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from backend.core.mission_checkpoint import MissionCheckpoint
from backend.core.mission_state import MissionState

logger = logging.getLogger(__name__)


class MissionInterruptHandler:
    """Manages interruption telemetry and initiates checkpoint restorations."""

    _active_executions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register_execution_start(cls, mission_id: str, stage: str) -> None:
        """Logs the start of a mission stage execution."""
        cls._active_executions[mission_id] = {
            "stage": stage,
            "start_time": time.time(),
            "status": "running"
        }
        logger.info("MissionInterruptHandler: Registered run start for mission '%s' at stage '%s'", mission_id, stage)

    @classmethod
    def register_execution_success(cls, mission_id: str) -> None:
        """Clears active run tracking upon successful completion."""
        if mission_id in cls._active_executions:
            del cls._active_executions[mission_id]
            logger.info("MissionInterruptHandler: Completed execution loop successfully for '%s'", mission_id)

    @classmethod
    def detect_and_handle_interruption(cls, mission_id: str) -> Dict[str, Any]:
        """Checks if the mission crashed or was interrupted, and restores from the latest checkpoint."""
        exec_info = cls._active_executions.get(mission_id)
        if not exec_info:
            return {"status": "clean", "message": "No active interruption detected."}

        # Interrupted!
        logger.warning(
            "MissionInterruptHandler: Interruption detected for mission '%s' (started: %.1f). Resuming...",
            mission_id, exec_info["start_time"]
        )

        # 1. Fetch checkpoints
        checkpoints = MissionCheckpoint.get_checkpoints_for_mission(mission_id)
        if not checkpoints:
            return {
                "status": "failed",
                "message": f"Cannot resume mission '{mission_id}': No checkpoints available."
            }

        # 2. Get latest checkpoint
        checkpoints.sort(key=lambda c: c["timestamp"])
        latest = checkpoints[-1]
        
        # 3. Restore state
        restored_state = MissionCheckpoint.rollback_to_checkpoint(mission_id, latest["checkpoint_id"])
        
        # 4. Clear execution crash trace
        del cls._active_executions[mission_id]

        return {
            "status": "resumed",
            "checkpoint_id": latest["checkpoint_id"],
            "restored_state": restored_state,
            "message": f"Successfully restored mission '{mission_id}' to stage '{latest['stage']}'."
        }
