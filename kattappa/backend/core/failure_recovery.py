from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.mission_state import MissionState


def _failure_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "failure_recovery.json"


class FailureRecoveryEngine:
    _lock = threading.RLock()

    @classmethod
    def load_failures(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _failure_file_path()
            if not path.exists():
                # Seed defaults
                initial = [
                    {
                        "failure_id": "fail_drone_001",
                        "mission_id": "mis_drone_jam",
                        "stage": "Design",
                        "agent": "Coder",
                        "reason": "Vite React component compilation timed out.",
                        "recovery_path": "Re-run build after optimizing node modules caching.",
                        "timestamp": time.time() - 4000,
                        "resolved": True,
                        "retry_count": 1
                    }
                ]
                cls.save_failures(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_failures(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _failure_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def trigger_failure(cls, mission_id: str, stage: str, agent: str, reason: str) -> dict[str, Any]:
        with cls._lock:
            failures = cls.load_failures()
            
            # Count recent failures for this stage in this mission to increment retry counts
            recent_retries = sum(1 for f in failures if f["mission_id"] == mission_id and f["stage"] == stage and not f["resolved"])
            retry_count = recent_retries + 1
            
            # Generate RCA and alternative path dynamically using LLM recovery worker
            from backend.core.model_router import ask_model
            import re
            
            prompt = (
                f"You are the Kattappa AI OS Failure Recovery and Replanning Engine.\n"
                f"Mission ID: {mission_id}\n"
                f"Stage: {stage}\n"
                f"Agent: {agent}\n"
                f"Failure Reason: {reason}\n\n"
                f"Task: Perform a brief root-cause analysis (RCA) and generate a practical alternative recovery path/action plan. "
                f"Return a JSON object with two fields:\n"
                f"1. 'rca': a summary of the root cause.\n"
                f"2. 'recovery_path': a specific, actionable instruction or sequence of steps to recover or bypass this failure.\n"
                f"Do not return any markdown wrappers, just the raw JSON object."
            )
            def _get_fallback_recovery(r_text: str) -> str:
                r_lower = r_text.lower()
                if "compile" in r_lower or "syntax" in r_lower or "react" in r_lower:
                    return "Scan target files for syntax issues, apply corrective patches, and retry tests."
                elif "timeout" in r_lower or "network" in r_lower or "port" in r_lower:
                    return "Re-check connection stability, expand timeout parameters to 15s, and run request again."
                return "Fallback to generic validation checks, retrieve last safe checkpoint, and ask human clearance."

            try:
                response = ask_model(prompt, role="recovery")
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    rca_reason = data.get("rca", f"RCA Analysis: {agent} agent failed due to: {reason}")
                    recovery_path = data.get("recovery_path")
                    if not recovery_path or "fallback to generic" in recovery_path.lower():
                        recovery_path = _get_fallback_recovery(reason)
                else:
                    rca_reason = f"RCA Analysis: {agent} agent failed due to: {reason}"
                    recovery_path = _get_fallback_recovery(reason)
            except Exception:
                rca_reason = f"RCA Analysis: {agent} agent failed due to: {reason}"
                recovery_path = _get_fallback_recovery(reason)
                
            fail_id = f"fail_{int(time.time())}_{len(failures)}"
            failure_report = {
                "failure_id": fail_id,
                "mission_id": mission_id,
                "stage": stage,
                "agent": agent,
                "reason": rca_reason,
                "recovery_path": recovery_path,
                "timestamp": time.time(),
                "resolved": False,
                "retry_count": retry_count
            }
            failures.append(failure_report)
            cls.save_failures(failures)
            
            # Set blocker on mission state
            MissionState.set_blocked(mission_id, blocked=True, blocker=f"Failure: {reason[:60]}")
            
            # If retry count >= 3, freeze the mission into failed state
            if retry_count >= 3:
                MissionState.update_progress(mission_id, progress=0.0) # Reset progress or mark failed
                # Update status in mission state
                state = MissionState.get_state(mission_id)
                if state:
                    state["status"] = "failed"
                    state["blockers"] = ["Unrecoverable stage failures (Max retries exceeded)"]
                    MissionState.set_state(mission_id, state)
            else:
                # Update status in mission state to waiting approval for alternative path
                state = MissionState.get_state(mission_id)
                if state:
                    state["status"] = "waiting_approval"
                    MissionState.set_state(mission_id, state)
                    
            return failure_report

    @classmethod
    def resolve_failure(cls, failure_id: str) -> None:
        with cls._lock:
            failures = cls.load_failures()
            for f in failures:
                if f["failure_id"] == failure_id:
                    f["resolved"] = True
                    # Clear blocker on mission state
                    MissionState.set_blocked(f["mission_id"], blocked=False)
                    # Resume mission state status to running
                    state = MissionState.get_state(f["mission_id"])
                    if state:
                        state["status"] = "running"
                        MissionState.set_state(f["mission_id"], state)
            cls.save_failures(failures)
