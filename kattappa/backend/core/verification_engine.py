from __future__ import annotations

import os
import time
import json
import re
import uuid
import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from backend.core.config import runtime_data_root
from backend.core.capability_registry import CapabilityRegistry, ACTION_CAPABILITY_MAP
from backend.core.resource_governor import ResourceGovernor
from backend.core.safety import is_protected_path


class VerificationCheckType(str, Enum):
    CRITICAL = "critical"
    SUPPORTING = "supporting"


@dataclass
class VerificationCheck:
    name: str
    check_type: VerificationCheckType
    eval_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any], Any], tuple[bool, Any]]


class VerificationProfile:
    def __init__(self, action: str, checks: list[VerificationCheck]):
        self.action = action.upper()
        self.checks = checks


# ---------------------------------------------------------------------------
# Default Verification Profiles
# ---------------------------------------------------------------------------

def _file_exists_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    target = params.get("target") or params.get("path") or params.get("destination")
    if not target:
        return False, "No target path specified"
    exists = os.path.exists(target)
    return exists, {"exists": exists, "path": target}


def _file_size_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    target = params.get("target") or params.get("path") or params.get("destination")
    if not target or not os.path.exists(target):
        return False, "File does not exist or target not specified"
    size = os.path.getsize(target)
    return size > 0, {"size": size, "path": target}


def _file_checksum_changed_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    c0 = s0.get("file_checksum")
    c1 = s1.get("file_checksum")
    changed = c0 != c1
    return changed, {"previous_checksum": c0, "current_checksum": c1}


def _file_deleted_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    target = params.get("target") or params.get("path") or params.get("destination")
    if not target:
        return False, "No target path specified"
    exists = os.path.exists(target)
    return not exists, {"exists": exists, "path": target}


def _memory_written_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    # Check if a new record is written
    from backend.core.human_memory import HumanMemoryStore
    content = params.get("content") or ""
    if not content:
        return False, "No content specified in memory write"

    # Try to find memory entry containing the content
    records = HumanMemoryStore.all_records()
    matched = any(content in r.content for r in records)
    return matched, {"content_matched": matched}


def _memory_version_updated_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    # Check if version count in SQLite has increased
    v0 = s0.get("memory_version_count", 0)
    v1 = s1.get("memory_version_count", 0)
    return v1 > v0, {"previous_version_count": v0, "current_version_count": v1}


def _browser_url_reached_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    url = params.get("url")
    if not url:
        return False, "No URL specified"
    # In test mode or simulated execution, we verify if the result indicates page load success
    success = isinstance(res, dict) and res.get("success", False)
    return success, {"target_url": url, "result_success": success}


def _desktop_process_running_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    target_app = params.get("app") or params.get("text") or ""
    # In test mode, we verify if the result shows success or process exists
    success = isinstance(res, dict) and res.get("success", False)
    return success, {"app": target_app, "success": success}


def _voice_stt_completed_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    success = isinstance(res, dict) and res.get("success", False)
    return success, {"stt_success": success}


def _voice_tts_completed_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    success = isinstance(res, dict) and res.get("success", False)
    return success, {"tts_success": success}


def _test_execution_completed_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    success = isinstance(res, dict) and res.get("success", False)
    return success, {"test_success": success}


def _shell_execution_completed_eval(params: dict, s0: dict, s1: dict, res: Any) -> tuple[bool, Any]:
    success = isinstance(res, dict) and res.get("success", False)
    return success, {"shell_success": success}


VERIFICATION_PROFILES = {
    "CREATE_FILE": VerificationProfile("CREATE_FILE", [
        VerificationCheck("File Exists", VerificationCheckType.CRITICAL, _file_exists_eval),
        VerificationCheck("File Size > 0", VerificationCheckType.SUPPORTING, _file_size_eval),
    ]),
    "WRITE_FILE": VerificationProfile("WRITE_FILE", [
        VerificationCheck("File Exists", VerificationCheckType.CRITICAL, _file_exists_eval),
        VerificationCheck("File Size > 0", VerificationCheckType.SUPPORTING, _file_size_eval),
    ]),
    "FILE_WRITE": VerificationProfile("FILE_WRITE", [
        VerificationCheck("File Exists", VerificationCheckType.CRITICAL, _file_exists_eval),
        VerificationCheck("File Size > 0", VerificationCheckType.SUPPORTING, _file_size_eval),
    ]),
    "FILE_MODIFY": VerificationProfile("FILE_MODIFY", [
        VerificationCheck("File Exists", VerificationCheckType.CRITICAL, _file_exists_eval),
        VerificationCheck("Checksum Changed", VerificationCheckType.SUPPORTING, _file_checksum_changed_eval),
    ]),
    "PATCH_CODE": VerificationProfile("PATCH_CODE", [
        VerificationCheck("File Exists", VerificationCheckType.CRITICAL, _file_exists_eval),
        VerificationCheck("Checksum Changed", VerificationCheckType.SUPPORTING, _file_checksum_changed_eval),
    ]),
    "DELETE_FILE": VerificationProfile("DELETE_FILE", [
        VerificationCheck("File Absent", VerificationCheckType.CRITICAL, _file_deleted_eval),
    ]),
    "FILE_DELETE": VerificationProfile("FILE_DELETE", [
        VerificationCheck("File Absent", VerificationCheckType.CRITICAL, _file_deleted_eval),
    ]),
    "COMMIT_MEMORY_DELTA": VerificationProfile("COMMIT_MEMORY_DELTA", [
        VerificationCheck("Memory Record Found", VerificationCheckType.CRITICAL, _memory_written_eval),
        VerificationCheck("Version Chains Updated", VerificationCheckType.SUPPORTING, _memory_version_updated_eval),
    ]),
    "BROWSER_NAVIGATE": VerificationProfile("BROWSER_NAVIGATE", [
        VerificationCheck("URL Reached", VerificationCheckType.CRITICAL, _browser_url_reached_eval),
    ]),
    "BROWSER_SEARCH": VerificationProfile("BROWSER_SEARCH", [
        VerificationCheck("Search Successful", VerificationCheckType.CRITICAL, _browser_url_reached_eval),
    ]),
    "DESKTOP_OPEN_APP": VerificationProfile("DESKTOP_OPEN_APP", [
        VerificationCheck("Process Running", VerificationCheckType.CRITICAL, _desktop_process_running_eval),
    ]),
    "VOICE_STT": VerificationProfile("VOICE_STT", [
        VerificationCheck("Transcription Success", VerificationCheckType.CRITICAL, _voice_stt_completed_eval),
    ]),
    "VOICE_TTS": VerificationProfile("VOICE_TTS", [
        VerificationCheck("Synthesis Success", VerificationCheckType.CRITICAL, _voice_tts_completed_eval),
    ]),
    "RUN_TESTS": VerificationProfile("RUN_TESTS", [
        VerificationCheck("Tests Completed", VerificationCheckType.CRITICAL, _test_execution_completed_eval),
    ]),
    "RUN_SHELL": VerificationProfile("RUN_SHELL", [
        VerificationCheck("Shell Command Ran", VerificationCheckType.CRITICAL, _shell_execution_completed_eval),
    ]),
}


# ---------------------------------------------------------------------------
# Verification Engine Class
# ---------------------------------------------------------------------------

class VerificationEngine:
    MUTATING_ACTIONS = {
        "WRITE_FILE", "CREATE_FILE", "EDIT_FILE", "FILE_WRITE", "FILE_MODIFY",
        "DELETE_FILE", "FILE_DELETE", "PATCH_CODE", "COMMIT_MEMORY_DELTA", "PIN_MEMORY"
    }

    @staticmethod
    def _evidence_path() -> Path:
        return runtime_data_root() / "backend" / "data" / "verification_evidence.json"

    @staticmethod
    def _rollback_stack_path() -> Path:
        return runtime_data_root() / "backend" / "data" / "rollback_stack.json"

    @classmethod
    def _log_audit(cls, agent: str, action: str, event: str, details: str) -> None:
        try:
            # Append to standard broker audit log
            from backend.core.action_broker import ActionBroker
            ActionBroker.log_audit_trail(agent, action, "verified", event, details)
        except Exception:
            pass

    # ----- Layer 1: Plan Verification -----

    @classmethod
    def verify_plan(cls, state: dict[str, Any]) -> dict[str, Any]:
        """Validates sequential dependencies, capability alignment, resources, safety, and rollbacks."""
        task_graph_data = state.get("task_graph")
        if not task_graph_data:
            return {"success": True}

        from backend.agents.planner import TaskGraph, TaskStep
        graph = TaskGraph(state.get("user_input") or "")

        try:
            # Reconstruct TaskGraph
            for step_id, step_data in task_graph_data.items():
                step = TaskStep(
                    step_id=step_id,
                    description=step_data.get("description", ""),
                    agent=step_data.get("agent", ""),
                    action=step_data.get("action", ""),
                    params=step_data.get("params", {}),
                    dependencies=step_data.get("dependencies", []),
                    risk_level=step_data.get("risk_level", "LOW"),
                    approval_required=step_data.get("approval_required", False),
                    estimated_resources=step_data.get("estimated_resources"),
                    failure_recovery=step_data.get("failure_recovery"),
                    rollback_step=step_data.get("rollback_step")
                )
                graph.add_step(step)

            order = graph.topological_sort()
        except ValueError as e:
            cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Dependency cycle detected: {e}")
            return {"success": False, "error": f"Plan Dependency Error: Circular dependency detected: {e}"}

        # 1. Sequential Dependency Analysis
        target_paths: dict[str, list[str]] = {}
        for step_id in order:
            step = graph.get_step(step_id)
            params = step.params or {}
            target = params.get("target") or params.get("path")
            if target:
                target_paths.setdefault(target, []).append(step.action.upper())

        for target, actions in target_paths.items():
            create_indices = [i for i, act in enumerate(actions) if act in ("CREATE_FILE", "WRITE_FILE", "FILE_WRITE")]
            edit_indices = [i for i, act in enumerate(actions) if act in ("EDIT_FILE", "FILE_MODIFY", "SAVE_FILE", "PATCH_CODE")]
            read_indices = [i for i, act in enumerate(actions) if act in ("READ_FILE", "OPEN_FILE", "FILE_PARSE")]

            if create_indices and edit_indices:
                if min(create_indices) > min(edit_indices):
                    cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Invalid sequence: File '{target}' edited before it is created.")
                    return {"success": False, "error": f"Dependency Sequence Error: File '{target}' is modified before it is initialized/created."}

            if read_indices and edit_indices:
                if min(read_indices) > min(edit_indices):
                    cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Invalid sequence: File '{target}' edited before it is read.")
                    return {"success": False, "error": f"Dependency Sequence Error: File '{target}' is modified before it is read."}

        # 2. Capability & Risk Alignment
        for step_id in order:
            step = graph.get_step(step_id)
            required_cap = ACTION_CAPABILITY_MAP.get(step.action.upper())
            if required_cap:
                if not CapabilityRegistry.is_capability_allowed(step.agent, required_cap):
                    cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Capability mismatch: Agent '{step.agent}' lacks capability '{required_cap}' for '{step.action}'")
                    return {"success": False, "error": f"Capability Error: Agent '{step.agent}' does not have capability '{required_cap}' required for action '{step.action}'"}

        # 3. Resource Availability Attestation
        status = ResourceGovernor.get_status()
        for step_id in order:
            step = graph.get_step(step_id)
            est = step.estimated_resources or {}

            # Simulated check for resource availability
            if est.get("disk_bytes", 0) + status["disk_used_bytes"] > status["disk_limit_bytes"]:
                cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", "Disk quota limit verification failed")
                return {"success": False, "error": f"Resource Attestation Failed: Disk space required by step '{step.step_id}' exceeds limit."}

            if est.get("network_requests", 0) + status["network_requests"] > status["network_limit_requests"]:
                cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", "Network request quota verification failed")
                return {"success": False, "error": f"Resource Attestation Failed: Network requests limit exceeded."}

        # 4. Safety Verification
        from backend.core.action_broker import ActionBroker
        for step_id in order:
            step = graph.get_step(step_id)
            params = step.params or {}
            target = params.get("target") or params.get("path") or params.get("destination")
            if target:
                if not ActionBroker.is_safe_workspace_path(target):
                    cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Safety block: unsafe traversal path '{target}'")
                    return {"success": False, "error": f"Safety Verification Failed: Path '{target}' lies outside the allowed workspace."}
                if is_protected_path(target) and step.action.upper() in cls.MUTATING_ACTIONS:
                    cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Safety block: protected path modification '{target}'")
                    return {"success": False, "error": f"Safety Verification Failed: Modifying protected governance module '{target}' is prohibited."}

        # 5. Rollback Availability Verification
        for step_id in order:
            step = graph.get_step(step_id)
            if step.action.upper() in cls.MUTATING_ACTIONS:
                if not step.rollback_step:
                    cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_REJECTED", f"Rollback missing for mutating step '{step.step_id}'")
                    return {"success": False, "error": f"Rollback Availability Error: Mutating step '{step.step_id}' ('{step.action}') does not define a rollback action."}

        cls._log_audit("dve", "PLAN_VERIFICATION", "PLAN_VERIFIED", f"Plan containing {len(order)} steps verified successfully")
        return {"success": True}

    # ----- Layer 2: State Snapshot Engine -----

    @classmethod
    def take_state_snapshot(cls, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Captures target state S0 or S1 prior to or following execution."""
        snapshot: dict[str, Any] = {}
        action_upper = action.upper()

        # 1. File Snapshot
        target_file = params.get("target") or params.get("path") or params.get("destination")
        if target_file:
            exists = os.path.exists(target_file)
            snapshot["file_exists"] = exists
            if exists:
                try:
                    snapshot["file_size"] = os.path.getsize(target_file)
                    snapshot["file_mtime"] = os.path.getmtime(target_file)
                    # Checksum of small text/code file
                    if snapshot["file_size"] < 5 * 1024 * 1024:
                        with open(target_file, "rb") as f:
                            snapshot["file_checksum"] = hashlib.md5(f.read()).hexdigest()
                except Exception:
                    pass

        # 2. Memory Database Snapshot
        if "MEMORY" in action_upper or "WRITE" in action_upper:
            try:
                from backend.core.human_memory import HumanMemoryStore
                snapshot["memory_record_count"] = HumanMemoryStore.count()
                conn = HumanMemoryStore._connect()
                # Check version table count
                row = conn.execute("SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name='hm_memory_versions'").fetchone()
                if row and row["c"] > 0:
                    snapshot["memory_version_count"] = conn.execute("SELECT COUNT(*) AS c FROM hm_memory_versions").fetchone()["c"]
                else:
                    snapshot["memory_version_count"] = 0
            except Exception:
                pass

        # 3. Process Snapshot
        if "DESKTOP" in action_upper:
            try:
                import psutil
                snapshot["running_pids"] = [p.pid for p in psutil.process_iter()]
            except Exception:
                pass

        return snapshot

    # ----- Layer 2: Post-Execution Attestation & Scoring -----

    @classmethod
    def post_execute_action(
        cls,
        agent: str,
        action: str,
        params: dict[str, Any],
        res: Any,
        s0: dict[str, Any],
        s1: dict[str, Any],
        state: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculates confidence score, logs verification status, and triggers retry/rollback on failure."""
        action_upper = action.upper()
        profile = VERIFICATION_PROFILES.get(action_upper)

        # If no profile defined, we default to success if execution returned success
        if not profile:
            success = isinstance(res, dict) and res.get("success", False)
            score = 1.0 if success else 0.0
            outcome = "SUCCESS" if success else "FAILURE"
            cls._log_audit(agent, action, "CONFIDENCE_SCORE", f"Confidence: {score:.2f} (No profile)")
            return {"success": success, "confidence_score": score, "outcome": outcome}

        critical_passed = True
        critical_count = 0
        passed_supporting = 0
        total_supporting = 0

        checks_results = {}

        for check in profile.checks:
            passed, details = check.eval_fn(params, s0, s1, res)
            checks_results[check.name] = {"passed": passed, "details": details, "type": check.check_type.value}

            if check.check_type == VerificationCheckType.CRITICAL:
                critical_count += 1
                if not passed:
                    critical_passed = False
            else:
                total_supporting += 1
                if passed:
                    passed_supporting += 1

        # Confidence Score calculation
        if not critical_passed or (critical_count > 0 and not critical_passed):
            score = 0.0
        else:
            if total_supporting == 0:
                score = 1.0
            else:
                score = 0.60 + 0.40 * (passed_supporting / total_supporting)

        score = round(score, 2)
        cls._log_audit(agent, action, "CONFIDENCE_SCORE", f"Confidence Score: {score:.2f}")

        # Store verification evidence
        cls._store_evidence(agent, action, params, s0, s1, checks_results, score)

        if score >= 0.90:
            cls._log_audit(agent, action, "ACTION_VERIFIED", f"Action '{action}' passed post-verification.")

            # Save mutating steps to rollback compensation stack if it succeeded
            if action_upper in cls.MUTATING_ACTIONS:
                # Find task step to get rollback step
                task_graph = state.get("task_graph") or {}
                # Match current action by type/params
                for step_id, step_data in task_graph.items():
                    if step_data.get("action") == action and step_data.get("rollback_step"):
                        cls._push_rollback(step_id, step_data["rollback_step"], agent)
                        break

            return {"success": True, "confidence_score": score, "outcome": "SUCCESS"}

        elif score >= 0.60:
            cls._log_audit(agent, action, "ACTION_VERIFIED", f"Action '{action}' verification returned REVIEW warning. Score: {score:.2f}")
            return {"success": True, "confidence_score": score, "outcome": "REVIEW"}

        else:
            cls._log_audit(agent, action, "ACTION_FAILED", f"Action '{action}' failed post-verification. Score: {score:.2f}")

            # Trigger failure recovery subsystem (Layer 3)
            return cls._handle_failure_recovery(agent, action, params, res, state)

    # ----- Layer 3: Failure Recovery Subsystem -----

    @classmethod
    def _is_transient_failure(cls, action: str, res: Any) -> bool:
        """Determines if the failure is temporary (network, lock) vs permanent."""
        err_msg = ""
        if isinstance(res, dict) and "error" in res:
            err_msg = str(res["error"]).lower()
        elif isinstance(res, str):
            err_msg = res.lower()

        # Transient indicators
        transient_indicators = ("timeout", "locked", "busy", "connection refused", "try again", "temporary")
        return any(ind in err_msg for ind in transient_indicators)

    @classmethod
    def _handle_failure_recovery(cls, agent: str, action: str, params: dict[str, Any], res: Any, state: dict[str, Any]) -> dict[str, Any]:
        """Coordinates retry limits and reverse chronological rollbacks."""
        is_transient = cls._is_transient_failure(action, res)

        if is_transient:
            # Let ActionBroker coordinate the retry loop
            return {
                "success": False,
                "confidence_score": 0.00,
                "outcome": "FAILURE",
                "recovery_action": "RETRY",
                "error": f"Transient failure detected: {res.get('error') or res}"
            }

        # Permanent failure -> Trigger Emergency Rollback Chain immediately
        cls._log_audit(agent, action, "ROLLBACK_STARTED", f"Permanent failure in action '{action}'. Initiating emergency rollback.")
        rollback_res = cls.execute_rollback_chain(state)
        return {
            "success": False,
            "confidence_score": 0.00,
            "outcome": "FAILURE",
            "recovery_action": "ROLLBACK",
            "error": f"Permanent failure. Rollback executed: {rollback_res.get('message')}"
        }

    @classmethod
    def execute_rollback_chain(cls, state: dict[str, Any]) -> dict[str, Any]:
        """Undoes mutating operations in reverse chronological sequence."""
        stack = cls._load_rollback_stack()
        if not stack:
            cls._log_audit("dve", "ROLLBACK", "ROLLBACK_COMPLETED", "No actions to rollback.")
            return {"success": True, "message": "Rollback stack empty"}

        cls._log_audit("dve", "ROLLBACK", "ROLLBACK_STARTED", f"Rolling back {len(stack)} actions in reverse order.")

        from backend.core.action_broker import ActionBroker
        errors = []

        # Pop in reverse order (chronological stack -> reverse chronological rollback)
        while stack:
            item = stack.pop()
            step_id = item["step_id"]
            rollback_step = item["rollback_step"]
            r_agent = item["agent"]

            r_action = rollback_step["action"]
            r_params = rollback_step["params"]

            cls._log_audit("dve", r_action, "ROLLBACK_STEP", f"Undoing step {step_id}: {r_action} with {r_params}")

            # Setup approved flags on state so Action Broker doesn't trigger human approval blocks on rollback actions
            rb_state = dict(state)
            rb_state["approved"] = True
            rb_state["double_approved"] = True

            # Call Action Broker directly
            res = ActionBroker.intake_request(r_agent, r_action, r_params, rb_state)
            if not res.get("success"):
                errors.append(f"Rollback of {step_id} failed: {res.get('error')}")

        # Clear rollback stack file
        cls._save_rollback_stack([])

        if errors:
            cls._log_audit("dve", "ROLLBACK", "ROLLBACK_COMPLETED", f"Rollback finished with errors: {errors}")
            return {"success": False, "error": f"Rollback completed with errors: {errors}"}

        cls._log_audit("dve", "ROLLBACK", "ROLLBACK_COMPLETED", "Rollback completed successfully. Workspace restored.")
        return {"success": True, "message": "Workspace successfully restored to original state."}

    # ----- Persistence Helpers -----

    @classmethod
    def _store_evidence(
        cls,
        agent: str,
        action: str,
        params: dict[str, Any],
        s0: dict[str, Any],
        s1: dict[str, Any],
        checks: dict[str, Any],
        score: float
    ) -> None:
        try:
            path = cls._evidence_path()
            path.parent.mkdir(parents=True, exist_ok=True)

            if path.exists():
                evidence_store = json.loads(path.read_text(encoding="utf-8"))
            else:
                evidence_store = []

            evidence_store.append({
                "action_id": f"act_{uuid.uuid4().hex[:8]}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "target_agent": agent,
                "action": action,
                "params": params,
                "expected_state": s0,
                "observed_state": s1,
                "confidence_score": score,
                "checks": checks
            })

            path.write_text(json.dumps(evidence_store[-1000:], indent=2), encoding="utf-8") # limit to last 1000 entries
        except Exception:
            pass

    @classmethod
    def _load_rollback_stack(cls) -> list[dict[str, Any]]:
        try:
            path = cls._rollback_stack_path()
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    @classmethod
    def _save_rollback_stack(cls, stack: list[dict[str, Any]]) -> None:
        try:
            path = cls._rollback_stack_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(stack, indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def _push_rollback(cls, step_id: str, rollback_step: dict[str, Any], agent: str) -> None:
        stack = cls._load_rollback_stack()
        # Avoid duplicate pushes
        if any(item["step_id"] == step_id for item in stack):
            return
        stack.append({
            "step_id": step_id,
            "rollback_step": rollback_step,
            "agent": agent,
            "timestamp": time.time()
        })
        cls._save_rollback_stack(stack)

    @classmethod
    def clear_rollback_stack(cls) -> None:
        cls._save_rollback_stack([])

    # ----- Layer 4: Action-Level Database-Backed Verification Engine -----

    _lock = threading.Lock()
    _schema_ensured = False

    _criterion_registry: dict[str, Callable[[dict[str, Any], dict[str, Any]], bool]] = {
        "READ_FILE": lambda params, result: result.get("content") is not None if isinstance(result, dict) else False,
        "WRITE_FILE": lambda params, result: result.get("success") is True if isinstance(result, dict) else False,
        "FILE_WRITE": lambda params, result: result.get("success") is True if isinstance(result, dict) else False,
        "BROWSER_SEARCH": lambda params, result: len(result.get("results", [])) > 0 if (isinstance(result, dict) and isinstance(result.get("results"), list)) else False,
        "RUN_SHELL": lambda params, result: result.get("exit_code") == 0 if isinstance(result, dict) else False,
    }

    @classmethod
    def register_criterion(cls, action: str, fn: Callable[[dict[str, Any], dict[str, Any]], bool]) -> None:
        """Register a custom success criterion function for a given action name."""
        cls._criterion_registry[action.upper()] = fn

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        from backend.core.config import load_config
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "goal_memory.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_reports (
                report_id       TEXT PRIMARY KEY,
                queue_id        TEXT,
                action          TEXT NOT NULL,
                agent_name      TEXT NOT NULL,
                verdict         TEXT NOT NULL,          -- VERIFIED | PARTIAL | REFUTED | SKIPPED
                structural_pass INTEGER NOT NULL,
                criterion_pass  INTEGER NOT NULL,
                confidence      REAL NOT NULL,          -- 0.0–1.0
                evidence_json   TEXT NOT NULL DEFAULT '{}',
                failure_reason  TEXT,
                created_at      REAL NOT NULL,
                retractable     INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        conn.commit()

    @classmethod
    def verify_result(
        cls,
        queue_id: str,
        action: str,
        agent_name: str,
        params: dict[str, Any],
        result: Any
    ) -> dict[str, Any]:
        """Perform structural and semantic verification on action output, persisting the report."""
        action_upper = action.upper()
        structural_pass = 0
        criterion_pass = 0
        failure_reason = None

        # 1. Structural pass
        if isinstance(result, dict):
            if result.get("success") is True:
                structural_pass = 1
            else:
                failure_reason = result.get("error") or "Action result success field is False"
        else:
            failure_reason = f"Invalid result format: {type(result)}"

        # 2. Criterion pass
        if structural_pass == 1:
            criterion_fn = cls._criterion_registry.get(action_upper)
            if criterion_fn:
                try:
                    if criterion_fn(params, result):
                        criterion_pass = 1
                    else:
                        failure_reason = f"Criterion evaluation failed for {action_upper}"
                except Exception as e:
                    failure_reason = f"Criterion evaluation exception: {e}"
            else:
                criterion_pass = 1  # Default pass if no criteria registered
        else:
            criterion_pass = 0

        # 3. Confidence score & verdict
        if structural_pass == 1 and criterion_pass == 1:
            confidence = 1.0
            verdict = "VERIFIED"
        elif structural_pass == 1:
            confidence = 0.5
            verdict = "PARTIAL"
        else:
            confidence = 0.0
            verdict = "REFUTED"

        report_id = f"vr_{uuid.uuid4().hex[:8]}"
        now = time.time()

        conn = cls._get_sqlite_conn()
        try:
            # Check for retraction of conflicting reports
            target = params.get("target") or params.get("path") or params.get("destination")
            if target:
                rows = conn.execute(
                    "SELECT report_id, evidence_json FROM verification_reports WHERE verdict IN ('VERIFIED', 'PASS') AND retractable = 1 AND action = ?",
                    (action_upper,)
                ).fetchall()
                for r in rows:
                    try:
                        old_ev = json.loads(r["evidence_json"])
                        old_params = old_ev.get("params", {})
                        old_target = old_params.get("target") or old_params.get("path") or old_params.get("destination")
                        if old_target == target:
                            new_v = "SUPERSEDED" if verdict in ("VERIFIED", "PASS") else "RETRACTED"
                            conn.execute(
                                """
                                UPDATE verification_reports
                                SET verdict = ?, confidence = 0.5, failure_reason = ?
                                WHERE report_id = ?
                                """,
                                (new_v, f"Updated due to subsequent conflicting verification (queue_id={queue_id})", r["report_id"])
                            )
                    except Exception:
                        pass

            # Insert report
            evidence_json = json.dumps({
                "params": params,
                "result": result
            })

            conn.execute(
                """
                INSERT INTO verification_reports (
                    report_id, queue_id, action, agent_name, verdict,
                    structural_pass, criterion_pass, confidence, evidence_json,
                    failure_reason, created_at, retractable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    report_id, queue_id, action_upper, agent_name, verdict,
                    structural_pass, criterion_pass, confidence, evidence_json,
                    failure_reason, now
                )
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "report_id": report_id,
            "queue_id": queue_id,
            "action": action_upper,
            "agent_name": agent_name,
            "verdict": verdict,
            "structural_pass": bool(structural_pass),
            "criterion_pass": bool(criterion_pass),
            "confidence": confidence,
            "failure_reason": failure_reason,
            "created_at": now
        }

    @classmethod
    def get_report(cls, report_id: str) -> dict[str, Any] | None:
        """Retrieve a specific verification report."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM verification_reports WHERE report_id = ?", (report_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @classmethod
    def get_reports_for_action(cls, queue_id: str) -> list[dict[str, Any]]:
        """Retrieve all verification reports associated with a queue_id."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM verification_reports WHERE queue_id = ? ORDER BY created_at DESC", (queue_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def retract_report(cls, report_id: str, reason: str) -> bool:
        """Retract a report, setting the verdict to RETRACTED and setting confidence to 0.5."""
        conn = cls._get_sqlite_conn()
        try:
            row = conn.execute("SELECT retractable, verdict FROM verification_reports WHERE report_id = ?", (report_id,)).fetchone()
            if not row:
                return False
            if not row["retractable"]:
                return False

            conn.execute(
                """
                UPDATE verification_reports
                SET verdict = 'RETRACTED', confidence = 0.5, failure_reason = ?
                WHERE report_id = ?
                """,
                (f"Retracted: {reason}", report_id)
            )
            conn.commit()
            cls._log_audit("ve", "RETRACT_REPORT", "REPORT_RETRACTED", f"Report {report_id} retracted. Reason: {reason}")
            return True
        finally:
            conn.close()

    @classmethod
    def get_verdicts_summary(cls) -> dict[str, int]:
        """Aggregate report verdict counts for Cognitive Dashboard Tier 9."""
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute(
                "SELECT verdict, COUNT(*) as c FROM verification_reports GROUP BY verdict"
            ).fetchall()
            summary = {
                "VERIFIED": 0, "PARTIAL": 0, "REFUTED": 0, "SKIPPED": 0,
                "RETRACTED": 0, "SUPERSEDED": 0, "PASS": 0, "FAIL": 0
            }
            for r in rows:
                v = r["verdict"]
                if v in summary:
                    summary[v] = r["c"]
            return summary
        finally:
            conn.close()


# =============================================================================
# Step 8.5 — Goal-level Verification Engine (VE) Core
# =============================================================================

class VerificationState(str, Enum):
    VERIFIED     = "VERIFIED"
    PARTIAL      = "PARTIAL"
    FAILED       = "FAILED"
    UNVERIFIABLE = "UNVERIFIABLE"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True)
class GoalVerificationReport:
    """Read-only attestation package holding outcomes of the verification pipeline."""
    goal_id: str
    state: VerificationState
    confidence_score: float
    criteria_checked: dict[str, bool]
    constraints_checked: dict[str, Any]
    audit_passed: bool
    evidence_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "state": self.state.value,
            "confidence_score": self.confidence_score,
            "criteria_checked": self.criteria_checked,
            "constraints_checked": self.constraints_checked,
            "audit_passed": self.audit_passed,
            "evidence_summary": self.evidence_summary,
        }


class EvidenceEngine:
    """Evidence Engine (Rule 3) — Gathers files, logs, and API status packages.

    Never executes mutating operations. Verifier != Executor (Rule 1).
    """

    @classmethod
    def collect(
        cls,
        file_paths: list[str] | None = None,
        log_check_events: list[str] | None = None,
        api_responses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        evidence = {
            "files": {},
            "logs": [],
            "api_responses": api_responses or [],
            "timestamp": time.time(),
        }

        if file_paths:
            for path in file_paths:
                exists = os.path.exists(path)
                file_info = {"exists": exists}
                if exists:
                    try:
                        file_info["size"] = os.path.getsize(path)
                        # Checksum calculation of small files
                        if file_info["size"] < 10 * 1024 * 1024:
                            with open(path, "rb") as f:
                                file_info["checksum"] = hashlib.md5(f.read()).hexdigest()
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                file_info["content"] = f.read(50 * 1024)  # first 50KB preview
                    except Exception as e:
                        file_info["error"] = str(e)
                evidence["files"][path] = file_info

        if log_check_events:
            for ev in log_check_events:
                evidence["logs"].append({
                    "event": ev,
                    "timestamp": time.time(),
                })

        return evidence


class SuccessCriteriaEngine:
    """Success Criteria Engine — Evaluates goal requirements checklist independently."""

    @classmethod
    def evaluate(cls, criteria: dict[str, Any], evidence: dict[str, Any]) -> dict[str, bool]:
        results = {}
        for key, expected_val in criteria.items():
            # Check file presence
            if key.startswith("file_exists:"):
                path = key.split("file_exists:", 1)[1].strip()
                file_info = evidence.get("files", {}).get(path, {})
                results[key] = file_info.get("exists", False) == bool(expected_val)

            # Check file substring presence
            elif key.startswith("file_contains:"):
                parts = key.split("file_contains:", 1)[1].split("->", 1)
                path = parts[0].strip()
                substr = parts[1].strip() if len(parts) > 1 else str(expected_val)
                file_info = evidence.get("files", {}).get(path, {})
                content = file_info.get("content", "")
                results[key] = substr in content

            # Check API status
            elif key.startswith("api_status:"):
                endpoint = key.split("api_status:", 1)[1].strip()
                resps = evidence.get("api_responses", [])
                found = False
                for r in resps:
                    if r.get("endpoint") == endpoint:
                        found = (r.get("status_code") == expected_val)
                        break
                results[key] = found

            # Check log event trigger
            elif key.startswith("log_event:"):
                event_name = key.split("log_event:", 1)[1].strip()
                results[key] = any(event_name in str(l) for l in evidence.get("logs", []))

            else:
                # Generic fallback comparison
                results[key] = False

        return results


class ConstraintEngine:
    """Constraint Engine — Evaluates resources, safety paths, and boundary budgets."""

    @classmethod
    def validate(cls, constraints: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        results = {}

        # Time constraint check
        time_spent = evidence.get("time_spent_seconds", 0.0)
        max_time = constraints.get("max_time_seconds")
        if max_time is not None:
            results["time_limit"] = {
                "passed": time_spent <= max_time,
                "details": f"Spent {time_spent:.1f}s (Limit {max_time:.1f}s)"
            }

        # Budget constraint check
        cost = evidence.get("cost_tokens", 0)
        max_cost = constraints.get("max_cost_tokens")
        if max_cost is not None:
            results["cost_limit"] = {
                "passed": cost <= max_cost,
                "details": f"Spent {cost} tokens (Limit {max_cost} tokens)"
            }

        # Safety boundary checks
        safety_passed = True
        safety_details = []
        for path in evidence.get("files", {}).keys():
            try:
                from backend.core.action_broker import ActionBroker
                safe = ActionBroker.is_safe_workspace_path(path)
            except Exception:
                safe = True
            if not safe:
                safety_passed = False
                safety_details.append(f"Unsafe path detected: {path}")

        results["safety_limit"] = {
            "passed": safety_passed,
            "details": "; ".join(safety_details) if safety_details else "All files in safe paths"
        }

        return results


class AuditEngine:
    """Audit Engine — Independent checks for fabrication, sufficiency, and contradictions."""

    @classmethod
    def audit(
        cls,
        evidence: dict[str, Any],
        criteria_results: dict[str, bool],
        constraint_results: dict[str, Any]
    ) -> dict[str, Any]:
        issues = []

        # 1. Sufficiency check
        if not criteria_results:
            issues.append("Sufficiency warning: Zero criteria evaluated.")

        # 2. Contradiction detection
        for file_path, file_info in evidence.get("files", {}).items():
            if not file_info.get("exists", False):
                if file_info.get("size", 0) > 0 or "content" in file_info:
                    issues.append(f"Contradictory evidence: File '{file_path}' reported non-existent but has size or content.")
            elif file_info.get("size", 0) == 0 and len(file_info.get("content", "")) > 0:
                issues.append(f"Contradictory evidence: File '{file_path}' has size 0 but non-empty content preview.")

        # 3. Fabrication/Tampering check
        for file_path, file_info in evidence.get("files", {}).items():
            if file_info.get("exists", False):
                checksum = file_info.get("checksum", "")
                if checksum == "d41d8cd98f00b204e9800998ecf8427e" and file_info.get("size", 0) > 0:
                    issues.append(f"Fabrication warning: File '{file_path}' has non-zero size but empty MD5 checksum.")

        passed = len(issues) == 0
        return {
            "passed": passed,
            "issues": issues,
            "details": "Audit successful" if passed else f"Audit flags: {'; '.join(issues)}"
        }


class ConfidenceEngine:
    """Confidence Engine — Scores outcome packages between [0.0, 1.0]."""

    @classmethod
    def score(
        cls,
        criteria_results: dict[str, bool],
        constraint_results: dict[str, Any],
        audit_result: dict[str, Any]
    ) -> float:
        if not criteria_results:
            return 0.0

        # Base success score
        passed_criteria = sum(1 for v in criteria_results.values() if v)
        total_criteria = len(criteria_results)
        score = passed_criteria / total_criteria

        # Penalty deductions
        for c in constraint_results.values():
            if not c.get("passed", True):
                if "safety" in str(c.get("details", "")).lower() or "unsafe" in str(c.get("details", "")).lower():
                    return 0.0  # safety failure results in zero confidence
                score -= 0.20

        if not audit_result.get("passed", True):
            score -= 0.40

        return max(0.0, min(1.0, round(score, 2)))


class GoalVerificationEngine:
    """Goal Verification Engine — Pipeline orchestrator linking verified outcome trust back to HCE."""

    @classmethod
    def verify_goal(
        cls,
        goal_id: str,
        evidence_params: dict[str, Any],
        success_criteria: dict[str, Any],
        constraints: dict[str, Any] | None = None
    ) -> GoalVerificationReport:
        # 1. Collect evidence package
        file_paths = evidence_params.get("file_paths")
        log_check_events = evidence_params.get("log_check_events")
        api_responses = evidence_params.get("api_responses")

        evidence = EvidenceEngine.collect(file_paths, log_check_events, api_responses)
        evidence["time_spent_seconds"] = evidence_params.get("time_spent_seconds", 0.0)
        evidence["cost_tokens"] = evidence_params.get("cost_tokens", 0)

        # 2. Success criteria checkers
        criteria_results = SuccessCriteriaEngine.evaluate(success_criteria, evidence)

        # 3. Constraint checking
        constraints = constraints or {}
        constraint_results = ConstraintEngine.validate(constraints, evidence)

        # 4. Independent audit
        audit_res = AuditEngine.audit(evidence, criteria_results, constraint_results)

        # 5. Score confidence
        score = ConfidenceEngine.score(criteria_results, constraint_results, audit_res)

        # 6. Resolve verification state
        issues = audit_res.get("issues", [])
        has_contradictions = any("contradictory" in issue.lower() for issue in issues)
        safety_failed = not constraint_results.get("safety_limit", {}).get("passed", True)

        if has_contradictions:
            state = VerificationState.CONTRADICTED
        elif safety_failed:
            state = VerificationState.FAILED
        elif not criteria_results:
            state = VerificationState.UNVERIFIABLE
        elif score >= 0.90 and audit_res.get("passed", True):
            state = VerificationState.VERIFIED
        elif score >= 0.50:
            state = VerificationState.PARTIAL
        else:
            state = VerificationState.FAILED

        # 7. Update HCE trust metrics (Rule: verified outcomes update trust score)
        cls._update_hce_trust(goal_id, state)

        return GoalVerificationReport(
            goal_id=goal_id,
            state=state,
            confidence_score=score,
            criteria_checked=criteria_results,
            constraints_checked=constraint_results,
            audit_passed=audit_res.get("passed", True),
            evidence_summary=audit_res.get("details", "")
        )

    @classmethod
    def _update_hce_trust(cls, goal_id: str, state: VerificationState) -> None:
        """Resolution helper to link verified outcomes back to relationship metrics in HCE."""
        try:
            from backend.core.goal_memory import GoalMemory
            from backend.core.personal_project_manager import PersonalProjectManager
            from backend.core.human_conversation_engine import HCEStore, TrustRecoveryEngine

            conn = GoalMemory._get_sqlite_conn()
            row = conn.execute("SELECT project_id FROM projects WHERE linked_goal_id = ?", (goal_id,)).fetchone()
            conn.close()

            if row:
                project_id = row["project_id"]
                proj = PersonalProjectManager.get_project(project_id)
                if proj:
                    user_entity_id = proj.get("user_entity_id") or proj.get("entity_id")
                    if user_entity_id:
                        rel = HCEStore.get_relationship_by_entity(user_entity_id)
                        if rel:
                            rel_id = rel["relationship_id"]
                            if state == VerificationState.VERIFIED:
                                # Successful verification increases relationship trust score
                                metrics = HCEStore.get_metrics(rel_id)
                                if metrics:
                                    new_trust = min(100.0, metrics["trust_score"] + 2.0)
                                    HCEStore.update_metrics(rel_id, trust_score=new_trust)
                            elif state in (VerificationState.FAILED, VerificationState.CONTRADICTED):
                                # Failure decreases trust score
                                TrustRecoveryEngine.record_error(rel_id)
        except Exception:
            pass

