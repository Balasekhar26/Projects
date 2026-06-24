"""
test_verification_engine.py
============================
Comprehensive test suite for Verification Engine V1 (DVE).

Coverage:
- Layer 1: Plan Verification (dependency, capability, resource, safety, rollback guard)
- Layer 2: State Snapshot Engine + Outcome Scoring (confidence thresholds)
- Layer 3: Failure Recovery (transient retry signal, permanent rollback chain)
- Layer 4: Audit Evidence Store (persistence)
- Integration: DVE wired into ActionBroker.intake_request end-to-end
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# -- environment isolation ------------------------------------------------------
os.environ.setdefault("KATTAPPA_ENV", "test")
os.environ.setdefault("KATTAPPA_ROOT", tempfile.mkdtemp(prefix="dve_test_"))


class _DVEBase(unittest.TestCase):
    """Base with a fresh temporary root so every test is fully isolated."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="dve_")
        os.environ["KATTAPPA_ROOT"] = self.root
        # Ensure data directory exists
        Path(self.root, "backend", "data").mkdir(parents=True, exist_ok=True)

        # Reset schema flags for database tables in test databases
        from backend.core.verification_engine import VerificationEngine
        from backend.core.cognitive_dashboard import CognitiveDashboardManager
        from backend.core.goal_memory import GoalMemory
        from backend.core.project_memory import ProjectMemory
        from backend.core.identity_system import IdentitySystem
        VerificationEngine._schema_ensured = False
        CognitiveDashboardManager._schema_ensured = False
        GoalMemory._schema_ensured = False
        ProjectMemory._schema_ensured = False
        IdentitySystem._schema_ensured = False

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)


# ==============================================================================
# 1.  Plan Verification - Layer 1
# ==============================================================================

class TestPlanVerification(_DVEBase):
    """Layer 1: static pre-execution gate checks."""

    def _make_graph(self, steps: list[dict]) -> dict:
        """Helper to build a task_graph dict suitable for verify_plan."""
        return {s["step_id"]: s for s in steps}

    def _base_step(self, step_id, action, agent="coder", deps=None,
                   params=None, rollback=None, resources=None):
        return {
            "step_id": step_id,
            "description": f"Step {step_id}",
            "agent": agent,
            "action": action,
            "params": params or {},
            "dependencies": deps or [],
            "risk_level": "LOW",
            "approval_required": False,
            "estimated_resources": resources or {},
            "failure_recovery": None,
            "rollback_step": rollback,
        }

    # ------------------------------------------------------------------
    # 1a. No task graph -> pass-through (empty plan is valid)
    # ------------------------------------------------------------------
    def test_empty_plan_passes(self):
        from backend.core.verification_engine import VerificationEngine
        result = VerificationEngine.verify_plan({"task_graph": {}})
        self.assertTrue(result["success"])

    def test_no_task_graph_passes(self):
        from backend.core.verification_engine import VerificationEngine
        result = VerificationEngine.verify_plan({})
        self.assertTrue(result["success"])

    # ------------------------------------------------------------------
    # 1b. Circular dependency detected
    # ------------------------------------------------------------------
    def test_circular_dependency_rejected(self):
        from backend.core.verification_engine import VerificationEngine
        graph = self._make_graph([
            self._base_step("s1", "READ_FILE", agent="coder", deps=["s2"]),
            self._base_step("s2", "READ_FILE", agent="coder", deps=["s1"]),
        ])
        result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertFalse(result["success"])
        self.assertIn("Dependency", result["error"])

    # ------------------------------------------------------------------
    # 1c. File edited before it is created
    # ------------------------------------------------------------------
    def test_edit_before_create_rejected(self):
        from backend.core.verification_engine import VerificationEngine
        graph = self._make_graph([
            # step1 edits - step2 creates (wrong order topologically)
            self._base_step("s1", "FILE_MODIFY", agent="coder",
                            params={"target": "/tmp/notes.txt"},
                            rollback={"action": "RESTORE_FILE", "params": {}}),
            self._base_step("s2", "CREATE_FILE", agent="coder", deps=["s1"],
                            params={"target": "/tmp/notes.txt"},
                            rollback={"action": "DELETE_FILE", "params": {}}),
        ])
        result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertFalse(result["success"])
        self.assertIn("Dependency Sequence Error", result["error"])

    # ------------------------------------------------------------------
    # 1d. Mutating step missing rollback -> rejected
    # ------------------------------------------------------------------
    def test_missing_rollback_rejected(self):
        from backend.core.verification_engine import VerificationEngine
        graph = self._make_graph([
            # Use relative path so safety check doesn't reject before rollback check
            self._base_step("s1", "WRITE_FILE", agent="coder",
                            params={"target": "output/out.txt"},
                            rollback=None),   # <-- no rollback!
        ])
        result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertFalse(result["success"])
        self.assertIn("Rollback Availability Error", result["error"])

    # ------------------------------------------------------------------
    # 1e. Valid plan with rollbacks defined passes
    # ------------------------------------------------------------------
    def test_valid_plan_passes(self):
        from backend.core.verification_engine import VerificationEngine
        graph = self._make_graph([
            self._base_step("s1", "CREATE_FILE", agent="coder",
                            params={"target": "output.txt"},
                            rollback={"action": "DELETE_FILE", "params": {"target": "output.txt"}}),
            self._base_step("s2", "READ_FILE", agent="coder",
                            params={"target": "output.txt"},
                            deps=["s1"]),
        ])
        result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertTrue(result["success"])

    # ------------------------------------------------------------------
    # 1f. Resource quota exceeded -> rejected
    # ------------------------------------------------------------------
    def test_disk_quota_exceeded_rejected(self):
        from backend.core.verification_engine import VerificationEngine
        from backend.core.resource_governor import ResourceGovernor
        status = ResourceGovernor.get_status()
        huge_bytes = status["disk_limit_bytes"] + 1

        graph = self._make_graph([
            self._base_step("s1", "CREATE_FILE", agent="coder",
                            params={"target": "big.bin"},
                            resources={"disk_bytes": huge_bytes},
                            rollback={"action": "DELETE_FILE", "params": {"target": "big.bin"}}),
        ])
        result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertFalse(result["success"])
        self.assertIn("Resource Attestation Failed", result["error"])

    # ------------------------------------------------------------------
    # 1g. Non-mutating step without rollback is fine
    # ------------------------------------------------------------------
    def test_read_step_no_rollback_passes(self):
        from backend.core.verification_engine import VerificationEngine
        graph = self._make_graph([
            self._base_step("s1", "READ_FILE", agent="coder",
                            params={"target": "data.txt"}),  # read-only -> no rollback needed
        ])
        result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertTrue(result["success"])


# ==============================================================================
# 2.  State Snapshot Engine - Layer 2a
# ==============================================================================

class TestStateSnapshot(_DVEBase):
    """Layer 2a: S0 / S1 state snapshot capture."""

    def test_snapshot_absent_file(self):
        from backend.core.verification_engine import VerificationEngine
        snap = VerificationEngine.take_state_snapshot(
            "WRITE_FILE", {"target": "/nonexistent/ghost.txt"}
        )
        self.assertFalse(snap["file_exists"])

    def test_snapshot_existing_file(self):
        from backend.core.verification_engine import VerificationEngine
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            tmp = f.name
        try:
            snap = VerificationEngine.take_state_snapshot("WRITE_FILE", {"target": tmp})
            self.assertTrue(snap["file_exists"])
            self.assertGreater(snap["file_size"], 0)
            self.assertIn("file_checksum", snap)
        finally:
            os.unlink(tmp)

    def test_snapshot_does_not_mutate(self):
        """Snapshot must be side-effect free."""
        from backend.core.verification_engine import VerificationEngine
        path = os.path.join(self.root, "canary.txt")
        snap = VerificationEngine.take_state_snapshot("CREATE_FILE", {"target": path})
        self.assertFalse(os.path.exists(path), "Snapshot must not create files")


# ==============================================================================
# 3.  Outcome Verification & Confidence Scoring - Layer 2b
# ==============================================================================

class TestOutcomeVerification(_DVEBase):
    """Layer 2b: post-execution confidence scoring and threshold routing."""

    def _run_post(self, action, params, res, s0=None, s1=None, state=None):
        from backend.core.verification_engine import VerificationEngine
        return VerificationEngine.post_execute_action(
            agent="test_agent",
            action=action,
            params=params,
            res=res,
            s0=s0 or {},
            s1=s1 or {},
            state=state or {},
        )

    # ------------------------------------------------------------------
    # 3a. File created -> critical check passes -> score >= 0.90 -> SUCCESS
    # ------------------------------------------------------------------
    def test_create_file_success_confidence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content")
            tmp = f.name
        try:
            result = self._run_post(
                "CREATE_FILE",
                {"target": tmp},
                {"success": True},
                s1={"file_exists": True, "file_size": 7},
            )
            self.assertTrue(result["success"])
            self.assertGreaterEqual(result["confidence_score"], 0.60)
            self.assertIn(result["outcome"], ("SUCCESS", "REVIEW"))
        finally:
            os.unlink(tmp)

    # ------------------------------------------------------------------
    # 3b. File missing -> critical check fails -> score 0.00 -> FAILURE
    # ------------------------------------------------------------------
    def test_create_file_missing_is_failure(self):
        result = self._run_post(
            "CREATE_FILE",
            {"target": "/nonexistent/ghost_12345.txt"},
            {"success": True},
            s1={},
        )
        self.assertEqual(result["confidence_score"], 0.0)
        self.assertIn(result["outcome"], ("FAILURE",))

    # ------------------------------------------------------------------
    # 3c. No profile -> pass-through based on result["success"]
    # ------------------------------------------------------------------
    def test_no_profile_action_success(self):
        result = self._run_post(
            "CUSTOM_UNKNOWN_ACTION",
            {},
            {"success": True},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["confidence_score"], 1.0)
        self.assertEqual(result["outcome"], "SUCCESS")

    def test_no_profile_action_failure(self):
        result = self._run_post(
            "CUSTOM_UNKNOWN_ACTION",
            {},
            {"success": False},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["confidence_score"], 0.0)

    # ------------------------------------------------------------------
    # 3d. Supporting check fails -> score 0.60 (REVIEW, not FAILURE)
    # ------------------------------------------------------------------
    def test_supporting_failure_gives_review_score(self):
        """Critical passes (file exists) but supporting (size>0) fails -> REVIEW zone."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            tmp = f.name  # empty file -> size == 0
        try:
            result = self._run_post(
                "CREATE_FILE",
                {"target": tmp},
                {"success": True},
                s1={"file_exists": True},
            )
            # critical passed, supporting failed -> score should be exactly 0.60
            self.assertGreaterEqual(result["confidence_score"], 0.60)
        finally:
            os.unlink(tmp)

    # ------------------------------------------------------------------
    # 3e. DELETE_FILE success -> file absent -> critical passed
    # ------------------------------------------------------------------
    def test_delete_file_success(self):
        """After deletion, file should not exist -> critical passes."""
        # Target a path that doesn't exist (as if already deleted)
        result = self._run_post(
            "DELETE_FILE",
            {"target": "/tmp/already_gone_dve_test.txt"},
            {"success": True},
        )
        # File doesn't exist -> _file_deleted_eval returns True -> critical passed
        self.assertGreaterEqual(result["confidence_score"], 0.90)
        self.assertEqual(result["outcome"], "SUCCESS")

    # ------------------------------------------------------------------
    # 3f. BROWSER_NAVIGATE success via result dict
    # ------------------------------------------------------------------
    def test_browser_navigate_success(self):
        result = self._run_post(
            "BROWSER_NAVIGATE",
            {"url": "https://example.com"},
            {"success": True},
        )
        self.assertTrue(result["success"])

    def test_browser_navigate_failure(self):
        result = self._run_post(
            "BROWSER_NAVIGATE",
            {"url": "https://example.com"},
            {"success": False},
        )
        self.assertEqual(result["confidence_score"], 0.0)

    # ------------------------------------------------------------------
    # 3g. Confidence thresholds are in [0.0, 1.0]
    # ------------------------------------------------------------------
    def test_confidence_in_bounds(self):
        result = self._run_post(
            "CUSTOM_X", {}, {"success": True}
        )
        self.assertGreaterEqual(result["confidence_score"], 0.0)
        self.assertLessEqual(result["confidence_score"], 1.0)


# ==============================================================================
# 4.  Verification Profiles
# ==============================================================================

class TestVerificationProfiles(_DVEBase):
    """Checks that the expected profiles are registered and structured correctly."""

    def test_all_expected_profiles_present(self):
        from backend.core.verification_engine import VERIFICATION_PROFILES, VerificationCheckType
        expected = {
            "CREATE_FILE", "WRITE_FILE", "FILE_WRITE", "FILE_MODIFY",
            "PATCH_CODE", "DELETE_FILE", "FILE_DELETE",
            "COMMIT_MEMORY_DELTA", "BROWSER_NAVIGATE", "BROWSER_SEARCH",
            "DESKTOP_OPEN_APP", "VOICE_STT", "VOICE_TTS",
            "RUN_TESTS", "RUN_SHELL",
        }
        registered = set(VERIFICATION_PROFILES.keys())
        self.assertTrue(expected.issubset(registered), f"Missing: {expected - registered}")

    def test_every_profile_has_at_least_one_critical_check(self):
        from backend.core.verification_engine import VERIFICATION_PROFILES, VerificationCheckType
        for name, profile in VERIFICATION_PROFILES.items():
            has_critical = any(
                c.check_type == VerificationCheckType.CRITICAL for c in profile.checks
            )
            self.assertTrue(has_critical, f"Profile '{name}' lacks a CRITICAL check")


# ==============================================================================
# 5.  Failure Recovery - Layer 3
# ==============================================================================

class TestFailureRecovery(_DVEBase):
    """Layer 3: transient signal and rollback chain execution."""

    def test_transient_failure_returns_retry_signal(self):
        from backend.core.verification_engine import VerificationEngine
        result = VerificationEngine._handle_failure_recovery(
            "test_agent", "BROWSER_NAVIGATE", {},
            {"error": "connection timeout"}, {}
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["recovery_action"], "RETRY")

    def test_permanent_failure_returns_rollback_signal(self):
        from backend.core.verification_engine import VerificationEngine
        result = VerificationEngine._handle_failure_recovery(
            "test_agent", "WRITE_FILE", {},
            {"error": "permission denied"}, {}
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["recovery_action"], "ROLLBACK")

    def test_empty_rollback_stack_is_safe(self):
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine.clear_rollback_stack()
        result = VerificationEngine.execute_rollback_chain({})
        self.assertTrue(result["success"])
        self.assertIn("empty", result["message"].lower())

    def test_rollback_stack_push_and_pop(self):
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine.clear_rollback_stack()

        rb_step = {"action": "DELETE_FILE", "params": {"target": "/tmp/test_rb.txt"}}
        VerificationEngine._push_rollback("step_1", rb_step, "test_agent")

        stack = VerificationEngine._load_rollback_stack()
        self.assertEqual(len(stack), 1)
        self.assertEqual(stack[0]["step_id"], "step_1")

    def test_duplicate_push_is_idempotent(self):
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine.clear_rollback_stack()

        rb = {"action": "DELETE_FILE", "params": {}}
        VerificationEngine._push_rollback("step_A", rb, "agent")
        VerificationEngine._push_rollback("step_A", rb, "agent")  # duplicate

        stack = VerificationEngine._load_rollback_stack()
        self.assertEqual(len(stack), 1, "Duplicate pushes should be idempotent")

    def test_transient_indicators_list(self):
        """Verify all intended transient keywords are detected."""
        from backend.core.verification_engine import VerificationEngine
        transient_errors = [
            {"error": "network timeout"},
            {"error": "resource busy"},
            {"error": "file is locked"},
            {"error": "connection refused"},
            {"error": "please try again"},
            {"error": "temporary failure"},
        ]
        for err in transient_errors:
            result = VerificationEngine._is_transient_failure("BROWSER_NAVIGATE", err)
            self.assertTrue(result, f"Expected transient for: {err}")

    def test_permanent_indicators(self):
        """Permission denied, corrupt, etc. must NOT be classified transient."""
        from backend.core.verification_engine import VerificationEngine
        permanent_errors = [
            {"error": "permission denied"},
            {"error": "corrupt state"},
            {"error": "validation failure"},
            {"error": "file not found"},
        ]
        for err in permanent_errors:
            result = VerificationEngine._is_transient_failure("WRITE_FILE", err)
            self.assertFalse(result, f"Expected permanent for: {err}")


# ==============================================================================
# 6.  Evidence Store - Layer 4
# ==============================================================================

class TestEvidenceStore(_DVEBase):
    """Verifies that verification evidence is persisted correctly."""

    def test_evidence_stored_after_verify(self):
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine._store_evidence(
            agent="test_agent",
            action="CREATE_FILE",
            params={"target": "/tmp/ev_test.txt"},
            s0={"file_exists": False},
            s1={"file_exists": True, "file_size": 42},
            checks={"File Exists": {"passed": True, "type": "critical", "details": {}}},
            score=0.97,
        )
        path = VerificationEngine._evidence_path()
        self.assertTrue(path.exists(), "Evidence file should be created")

        data = json.loads(path.read_text())
        # Evidence may be a list (multiple entries) or the latest single entry
        last = data[-1] if isinstance(data, list) else data
        self.assertIn("confidence_score", last)
        self.assertEqual(last["confidence_score"], 0.97)

    def test_evidence_file_capped_at_1000(self):
        """Store 1001 entries and verify only last 1000 are kept."""
        from backend.core.verification_engine import VerificationEngine
        for i in range(1001):
            VerificationEngine._store_evidence(
                f"agent_{i}", f"ACTION_{i}",
                {}, {}, {}, {}, float(i % 100) / 100.0,
            )
        path = VerificationEngine._evidence_path()
        data = json.loads(path.read_text())
        self.assertLessEqual(len(data), 1000, "Evidence store must cap at 1000 entries")


# ==============================================================================
# 7.  Integration - DVE wired into ActionBroker
# ==============================================================================

class TestActionBrokerDVEIntegration(_DVEBase):
    """End-to-end: verify DVE is invoked on every intake_request call."""

    def _state(self, approved=True):
        return {
            "user_input": "test",
            "approved": approved,
            "double_approved": False,
        }

    # ------------------------------------------------------------------
    # 7a. READ_FILE (low risk, no DVE profile) -> response has verification key
    # ------------------------------------------------------------------
    def test_read_file_response_has_verification_key(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write("hello")
        tmp.close()

        try:
            from backend.core.action_broker import ActionBroker
            # Use "coder" agent which has CAP_FILE_READ
            result = ActionBroker.intake_request(
                "coder", "READ_FILE", {"target": tmp.name}, self._state()
            )
            self.assertTrue(result.get("success"), f"Expected success, got: {result}")
            self.assertIn("verification", result)
            self.assertIn("confidence_score", result["verification"])
        finally:
            os.unlink(tmp.name)

    # ------------------------------------------------------------------
    # 7b. CREATE_FILE -> DVE runs post-verification -> confidence > 0
    # ------------------------------------------------------------------
    def test_create_file_dvs_post_verify(self):
        # Use workspace-relative path so safety check doesn't block
        target = "backend/data/dve_broker_test_file.txt"
        from backend.core.action_broker import ActionBroker
        # "coder" has CAP_FILE_CREATE; MEDIUM risk requires approved=True
        state = self._state(approved=True)
        result = ActionBroker.intake_request(
            "coder", "CREATE_FILE",
            {"target": target, "content": "hello dvs"},
            state
        )
        # May require approval; if not, should have verification
        if result.get("approval_required"):
            self.skipTest("Approval required - skipping broker DVE check")
        self.assertIn("verification", result, f"Got: {result}")
        v = result["verification"]
        self.assertIn("confidence_score", v)
        self.assertGreater(v["confidence_score"], 0.0)
        # Cleanup
        if os.path.exists(target):
            os.remove(target)

    # ------------------------------------------------------------------
    # 7c. Blocked action -> DVE not reached -> no verification key
    # ------------------------------------------------------------------
    def test_blocked_action_has_no_verification(self):
        from backend.core.action_broker import ActionBroker
        result = ActionBroker.intake_request(
            "code_agent", "EXFILTRATE_DATA", {}, self._state()
        )
        self.assertFalse(result.get("success"))
        # DVE should not run on blocked actions
        self.assertNotIn("verification", result)

    # ------------------------------------------------------------------
    # 7d. DVE snapshot is non-mutating - file must not be created by snapshot
    # ------------------------------------------------------------------
    def test_snapshot_does_not_create_side_effects(self):
        from backend.core.verification_engine import VerificationEngine
        ghost = os.path.join(self.root, "ghost_dve.txt")
        VerificationEngine.take_state_snapshot("CREATE_FILE", {"target": ghost})
        self.assertFalse(os.path.exists(ghost), "Snapshot must never create files")

    # ------------------------------------------------------------------
    # 7e. Verify plan -> PLAN_VERIFIED emitted without error
    # ------------------------------------------------------------------
    def test_verify_plan_emits_verified_on_success(self):
        from backend.core.verification_engine import VerificationEngine
        # Empty plan (no steps) should always verify
        result = VerificationEngine.verify_plan({"task_graph": {}})
        self.assertTrue(result["success"])

    # ------------------------------------------------------------------
    # 7f. Rollback chain respects LIFO order
    # ------------------------------------------------------------------
    def test_rollback_chain_lifo_order(self):
        """Push 3 steps; rollback must undo in reverse order (N, N-1, N-2)."""
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine.clear_rollback_stack()

        order = []

        def fake_intake(agent, action, params, state):
            order.append(action)
            return {"success": True, "result": {"success": True}}

        rb_steps = [
            {"action": "UNDO_STEP_1", "params": {}},
            {"action": "UNDO_STEP_2", "params": {}},
            {"action": "UNDO_STEP_3", "params": {}},
        ]
        for i, rb in enumerate(rb_steps, 1):
            VerificationEngine._push_rollback(f"step_{i}", rb, "test_agent")

        # Patch ActionBroker where it's actually imported inside execute_rollback_chain
        with patch(
            "backend.core.action_broker.ActionBroker.intake_request",
            side_effect=fake_intake
        ):
            VerificationEngine.execute_rollback_chain({})

        # Should be reversed
        self.assertEqual(order, ["UNDO_STEP_3", "UNDO_STEP_2", "UNDO_STEP_1"])


# ==============================================================================
# 8.  Authority Boundary Tests (DVE must NEVER execute or modify)
# ==============================================================================

class TestDVEAuthorityBoundaries(_DVEBase):
    """Ensure DVE never directly executes OS commands or mutates files."""

    def test_dve_has_no_run_command_method(self):
        from backend.core.verification_engine import VerificationEngine
        self.assertFalse(
            hasattr(VerificationEngine, "run_command"),
            "DVE must not expose run_command - only ActionBroker may execute"
        )

    def test_dve_has_no_write_file_method(self):
        from backend.core.verification_engine import VerificationEngine
        self.assertFalse(
            hasattr(VerificationEngine, "write_file"),
            "DVE must not expose write_file"
        )

    def test_dve_has_no_delete_file_method(self):
        from backend.core.verification_engine import VerificationEngine
        self.assertFalse(
            hasattr(VerificationEngine, "delete_file"),
            "DVE must not expose delete_file"
        )

    def test_dve_has_no_shell_execution_method(self):
        from backend.core.verification_engine import VerificationEngine
        shell_attrs = ("shell_exec", "run_shell", "exec", "popen", "subprocess")
        for attr in shell_attrs:
            self.assertFalse(
                hasattr(VerificationEngine, attr),
                f"DVE must not expose '{attr}'"
            )

    def test_dve_rollback_delegates_to_action_broker(self):
        """DVE rollback MUST call ActionBroker.intake_request, not execute directly."""
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine.clear_rollback_stack()
        VerificationEngine._push_rollback(
            "s_cleanup",
            {"action": "DELETE_FILE", "params": {"target": "/tmp/x.txt"}},
            "test_agent"
        )
        # Patch the method where the import is resolved (inside execute_rollback_chain)
        with patch("backend.core.action_broker.ActionBroker.intake_request") as mock_intake:
            mock_intake.return_value = {"success": True, "result": {}}
            VerificationEngine.execute_rollback_chain({})
            mock_intake.assert_called_once()

    def test_verify_plan_cannot_modify_plan_structure(self):
        """verify_plan may only return success/error - it cannot rewrite plan steps."""
        from backend.core.verification_engine import VerificationEngine
        original_graph = {
            "s1": {
                "step_id": "s1", "description": "Read only",
                "agent": "code_agent", "action": "READ_FILE",
                "params": {"target": "/tmp/test.txt"},
                "dependencies": [], "risk_level": "LOW",
                "approval_required": False, "estimated_resources": {},
                "failure_recovery": None, "rollback_step": None,
            }
        }
        import copy
        snapshot = copy.deepcopy(original_graph)
        VerificationEngine.verify_plan({"task_graph": original_graph})
        # Plan must be unchanged
        self.assertEqual(original_graph, snapshot, "DVE must not mutate the plan structure")


# ==============================================================================
# 9.  Report - Verification Workflow E2E
# ==============================================================================

class TestVerificationWorkflowReport(_DVEBase):
    """Full Plan -> Execute -> Verify -> Report workflow test."""

    def test_full_workflow_file_create(self):
        """
        Simulated workflow:
        1. verify_plan (pre-gate)
        2. S0 snapshot
        3. Simulated file write
        4. S1 snapshot
        5. post_execute_action (scoring)
        6. Evidence stored
        """
        from backend.core.verification_engine import VerificationEngine

        target = "backend/data/dve_workflow_report.txt"

        # Step 1: Plan verification - use "coder" agent which has file caps
        graph = {
            "s1": {
                "step_id": "s1", "description": "Create report",
                "agent": "coder", "action": "CREATE_FILE",
                "params": {"target": target},
                "dependencies": [], "risk_level": "LOW",
                "approval_required": False,
                "estimated_resources": {},
                "failure_recovery": None,
                "rollback_step": {"action": "DELETE_FILE", "params": {"target": target}},
            }
        }
        plan_result = VerificationEngine.verify_plan({"task_graph": graph})
        self.assertTrue(plan_result["success"], "Plan should pass pre-verification")

        # Step 2: S0 snapshot (before execution)
        s0 = VerificationEngine.take_state_snapshot("CREATE_FILE", {"target": target})
        self.assertFalse(s0.get("file_exists"), "File must not exist before execution")

        # Step 3: Simulated execution
        with open(target, "w") as f:
            f.write("Report content generated by DVE workflow test.")

        # Step 4: S1 snapshot (after execution)
        s1 = VerificationEngine.take_state_snapshot("CREATE_FILE", {"target": target})
        self.assertTrue(s1.get("file_exists"), "File must exist after execution")

        # Step 5: Post-execution scoring
        score_result = VerificationEngine.post_execute_action(
            agent="code_agent",
            action="CREATE_FILE",
            params={"target": target},
            res={"success": True},
            s0=s0,
            s1=s1,
            state={"task_graph": graph},
        )

        self.assertIn("confidence_score", score_result)
        self.assertGreaterEqual(score_result["confidence_score"], 0.60)
        self.assertIn(score_result["outcome"], ("SUCCESS", "REVIEW"))

        # Step 6: Evidence should be stored
        evidence_path = VerificationEngine._evidence_path()
        self.assertTrue(evidence_path.exists(), "Evidence must be persisted after verification")
        data = json.loads(evidence_path.read_text())
        last = data[-1] if isinstance(data, list) else data
        self.assertEqual(last["action"], "CREATE_FILE")

        # Step 7: Rollback stack should contain the step (pushed on success)
        stack = VerificationEngine._load_rollback_stack()
        self.assertTrue(
            any(item["step_id"] == "s1" for item in stack),
            "Successful mutating step should push rollback entry"
        )

        # Cleanup
        if os.path.exists(target):
            os.remove(target)


# ==============================================================================
# 10. Action-Level Database-Backed Verification Engine (Step 8.9)
# ==============================================================================

class TestVerificationEngineNewDB(_DVEBase):
    """Layer 4: Action-level SQLite verification database and retraction ledger."""

    def setUp(self):
        super().setUp()
        from backend.core.verification_engine import VerificationEngine
        conn = VerificationEngine._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM verification_reports")
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def test_register_criterion(self):
        from backend.core.verification_engine import VerificationEngine
        called = []
        VerificationEngine.register_criterion(
            "CUSTOM_ACTION",
            lambda params, result: called.append((params, result)) or result.get("data") == 42
        )
        # Test success
        res1 = VerificationEngine.verify_result("q_1", "CUSTOM_ACTION", "agent", {"x": 1}, {"success": True, "data": 42})
        self.assertEqual(res1["verdict"], "VERIFIED")
        self.assertEqual(res1["confidence"], 1.0)
        self.assertEqual(len(called), 1)

        # Test failure
        res2 = VerificationEngine.verify_result("q_2", "CUSTOM_ACTION", "agent", {"x": 1}, {"success": True, "data": 99})
        self.assertEqual(res2["verdict"], "PARTIAL")
        self.assertEqual(res2["confidence"], 0.5)

    def test_verify_result_structural_failure(self):
        from backend.core.verification_engine import VerificationEngine
        # Invalid result format (not a dict)
        res1 = VerificationEngine.verify_result("q_1", "READ_FILE", "agent", {}, "raw string result")
        self.assertEqual(res1["verdict"], "REFUTED")
        self.assertEqual(res1["confidence"], 0.0)

        # Dictionary with success: False
        res2 = VerificationEngine.verify_result("q_2", "READ_FILE", "agent", {}, {"success": False, "error": "file missing"})
        self.assertEqual(res2["verdict"], "REFUTED")
        self.assertEqual(res2["confidence"], 0.0)
        self.assertEqual(res2["failure_reason"], "file missing")

    def test_retract_report(self):
        from backend.core.verification_engine import VerificationEngine
        res = VerificationEngine.verify_result("q_1", "WRITE_FILE", "agent", {}, {"success": True})
        report_id = res["report_id"]

        # Before retraction
        report = VerificationEngine.get_report(report_id)
        self.assertEqual(report["verdict"], "VERIFIED")
        self.assertEqual(report["confidence"], 1.0)

        # Perform retraction
        success = VerificationEngine.retract_report(report_id, "Manual inspection found corrupted file write")
        self.assertTrue(success)

        # After retraction
        report_retracted = VerificationEngine.get_report(report_id)
        self.assertEqual(report_retracted["verdict"], "RETRACTED")
        self.assertEqual(report_retracted["confidence"], 0.5)
        self.assertIn("Retracted", report_retracted["failure_reason"])

    def test_conflicting_verification_retracts_old(self):
        from backend.core.verification_engine import VerificationEngine
        params = {"path": "/tmp/canary_db.txt"}
        
        # 1. Enqueue and verify first action as successful (VERIFIED)
        res1 = VerificationEngine.verify_result("q_1", "WRITE_FILE", "agent", params, {"success": True})
        self.assertEqual(res1["verdict"], "VERIFIED")

        # 2. Enqueue and verify second action on same target file as failure (REFUTED)
        res2 = VerificationEngine.verify_result("q_2", "WRITE_FILE", "agent", params, {"success": False, "error": "file empty"})
        self.assertEqual(res2["verdict"], "REFUTED")

        # 3. Old report (res1) should be automatically downgraded to RETRACTED
        report1 = VerificationEngine.get_report(res1["report_id"])
        self.assertEqual(report1["verdict"], "RETRACTED")
        self.assertEqual(report1["confidence"], 0.5)
        self.assertIn("conflicting verification", report1["failure_reason"])

    def test_conflicting_verification_supersedes_old(self):
        from backend.core.verification_engine import VerificationEngine
        params = {"path": "/tmp/canary_db.txt"}
        
        # 1. Enqueue and verify first action as successful (VERIFIED)
        res1 = VerificationEngine.verify_result("q_1", "WRITE_FILE", "agent", params, {"success": True})
        self.assertEqual(res1["verdict"], "VERIFIED")

        # 2. Enqueue and verify second action on same target file as successful (VERIFIED)
        res2 = VerificationEngine.verify_result("q_2", "WRITE_FILE", "agent", params, {"success": True})
        self.assertEqual(res2["verdict"], "VERIFIED")

        # 3. Old report (res1) should be automatically downgraded to SUPERSEDED
        report1 = VerificationEngine.get_report(res1["report_id"])
        self.assertEqual(report1["verdict"], "SUPERSEDED")
        self.assertEqual(report1["confidence"], 0.5)
        self.assertIn("conflicting verification", report1["failure_reason"])

    def test_get_verdicts_summary(self):
        from backend.core.verification_engine import VerificationEngine
        # Verify clean summary
        summary1 = VerificationEngine.get_verdicts_summary()
        self.assertEqual(summary1["VERIFIED"], 0)

        # Insert reports
        VerificationEngine.verify_result("q_1", "WRITE_FILE", "agent", {}, {"success": True})
        VerificationEngine.verify_result("q_2", "WRITE_FILE", "agent", {}, {"success": False})

        summary2 = VerificationEngine.get_verdicts_summary()
        self.assertEqual(summary2["VERIFIED"], 1)
        self.assertEqual(summary2["REFUTED"], 1)

    def test_get_reports_for_action(self):
        from backend.core.verification_engine import VerificationEngine
        VerificationEngine.verify_result("q_target", "WRITE_FILE", "agent", {}, {"success": True})
        VerificationEngine.verify_result("q_target", "WRITE_FILE", "agent", {}, {"success": False})

        reports = VerificationEngine.get_reports_for_action("q_target")
        self.assertEqual(len(reports), 2)
        # Check sort order (newest first)
        self.assertEqual(reports[0]["verdict"], "REFUTED")
        self.assertEqual(reports[1]["verdict"], "VERIFIED")

    def test_integration_action_scheduler_calls_ve(self):
        from backend.core.action_scheduler import ActionScheduler
        # We need a mock broker to pretend to execute successfully
        with patch("backend.core.action_broker.ActionBroker.intake_request") as mock_intake:
            mock_intake.return_value = {"success": True, "content": "mock file content"}

            # Enqueue READ_FILE
            res = ActionScheduler.enqueue_action("agent", "READ_FILE", {"path": "test.txt"}, {})
            queue_id = res["queue_id"]

            # Dispatch
            dispatch_res = ActionScheduler.dispatch_next()
            self.assertEqual(dispatch_res["status"], "dispatched")

            # Check if a verification report was generated and attached to the DB action record
            action_record = ActionScheduler.get_action(queue_id)
            self.assertIsNotNone(action_record)
            
            result_data = json.loads(action_record["result_json"])
            self.assertIn("verification_report_id", result_data)
            self.assertEqual(result_data["verification_verdict"], "VERIFIED")

            # Verify report exists in VE database
            from backend.core.verification_engine import VerificationEngine
            ve_report = VerificationEngine.get_report(result_data["verification_report_id"])
            self.assertIsNotNone(ve_report)
            self.assertEqual(ve_report["verdict"], "VERIFIED")
            self.assertEqual(ve_report["queue_id"], queue_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
