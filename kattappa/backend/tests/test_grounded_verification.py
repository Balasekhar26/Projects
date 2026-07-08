"""Unit tests for Program 18.1: Grounded Action Verification Layer.

Verifies ActionExpectation, StateDiffer, RecoveryPolicy, and custom Visual VerificationEngine routing.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.core.perception.action_expectation import ActionExpectation, get_expectation_for_action
from backend.core.perception.state_differ import StateDiffer
from backend.core.perception.recovery_policy import RecoveryPolicy
from backend.core.perception.screen_graph import ScreenGraph
from backend.core.verification_engine import VerificationEngine


# ── 1. ActionExpectation Evaluator ────────────────────────────────────────────

class TestActionExpectation:
    def test_url_matching(self):
        exp = ActionExpectation(expected_url="dashboard")
        assert exp.evaluate_match([], current_url="http://localhost/dashboard") == 1.0
        assert exp.evaluate_match([], current_url="http://localhost/home") == 0.0

    def test_text_presence_and_absence(self):
        exp = ActionExpectation(
            expected_text_present=["Welcome", "Status: Active"],
            expected_text_absent=["critical error", "crash"]
        )

        observed = ["welcome, user!", "Status: Active", "healthy system"]
        # All present matched, no absent text found -> 4/4 matches -> 1.0
        assert exp.evaluate_match(observed) == 1.0

        # One expected text missing -> 3/4 matches -> 0.75
        observed_partial = ["welcome, user!", "healthy system"]
        assert exp.evaluate_match(observed_partial) == 0.75

        # Absent text found -> 3/4 matches -> 0.75
        observed_failed = ["welcome, user!", "Status: Active", "critical error occurred"]
        assert exp.evaluate_match(observed_failed) == 0.75

    def test_get_expectation_for_action(self):
        params = {"expect_text_present": "Save Success", "expect_timeout_ms": 2000}
        exp = get_expectation_for_action("BROWSER_CLICK", params)
        assert exp.expected_text_present == ["Save Success"]
        assert exp.max_wait_ms == 2000


# ── 2. StateDiffer Delta Engine ────────────────────────────────────────────────

class TestStateDiffer:
    def test_diff_graphs_deltas(self):
        before_regions = [
            {"text": "Submit", "x": 100, "y": 200, "w": 50, "h": 20, "confidence": 99.0},
            {"text": "Persist", "x": 500, "y": 10, "w": 40, "h": 20, "confidence": 99.0},
        ]
        after_regions = [
            # Persist moved by 30px
            {"text": "Persist", "x": 530, "y": 10, "w": 40, "h": 20, "confidence": 99.0},
            {"text": "Alert: Save Complete", "x": 300, "y": 300, "w": 100, "h": 25, "confidence": 99.0},
        ]

        before_graph = ScreenGraph(before_regions)
        after_graph = ScreenGraph(after_regions)

        diff = StateDiffer.diff_graphs(before_graph, after_graph)
        assert "Alert: Save Complete" in diff["added_texts"]
        assert "Submit" in diff["removed_texts"]
        assert len(diff["moved_elements"]) == 1
        assert diff["moved_elements"][0]["text"] == "Persist"
        assert diff["modal_opened"] is True


# ── 3. RecoveryPolicy Strategies ──────────────────────────────────────────────

class TestRecoveryPolicy:
    def test_recovery_on_modal(self):
        diff = {"modal_opened": True, "added_texts": [], "removed_texts": []}
        dec = RecoveryPolicy.evaluate_recovery("BROWSER_CLICK", {}, diff, 1.0)
        assert dec["recovery_action"] == "DISMISS_MODAL"

    def test_recovery_on_transient_score(self):
        diff = {"modal_opened": False, "added_texts": [], "removed_texts": []}
        dec = RecoveryPolicy.evaluate_recovery("BROWSER_CLICK", {}, diff, 0.75)
        assert dec["recovery_action"] == "RETRY"

    def test_recovery_on_critical_error(self):
        diff = {
            "modal_opened": False,
            "added_texts": ["Fatal Error Occurred", "Access Denied"],
            "removed_texts": []
        }
        dec = RecoveryPolicy.evaluate_recovery("BROWSER_CLICK", {}, diff, 0.0)
        assert dec["recovery_action"] == "REPLAN"


# ── 4. VerificationEngine Integration ─────────────────────────────────────────

class TestVerificationEngineGrounded:
    def test_post_execute_action_verification_success(self):
        # S0 / S1 layout mocks
        s0_graph = ScreenGraph([{"text": "Submit", "x": 10, "y": 20, "w": 30, "h": 10, "confidence": 99.0}])
        s1_graph = ScreenGraph([{"text": "Success Banner", "x": 10, "y": 20, "w": 30, "h": 10, "confidence": 99.0}])

        s0 = {"screen_graph": s0_graph}
        s1 = {"screen_graph": s1_graph}

        params = {"expect_text_present": "Success Banner"}
        res = {"success": True}

        # Verify that verification engine computes high confidence
        report = VerificationEngine.post_execute_action(
            agent="Browser",
            action="BROWSER_CLICK",
            params=params,
            res=res,
            s0=s0,
            s1=s1,
            state={"task_graph": {}}
        )

        assert report["success"] is True
        assert report["outcome"] == "SUCCESS"
        assert report["confidence_score"] >= 0.90

    def test_post_execute_action_verification_failure_replan(self):
        s0_graph = ScreenGraph([{"text": "Submit", "x": 10, "y": 20, "w": 30, "h": 10, "confidence": 99.0}])
        # Unrelated text matches, but contains critical error text
        s1_graph = ScreenGraph([{"text": "Fatal Error Page", "x": 10, "y": 20, "w": 30, "h": 10, "confidence": 99.0}])

        s0 = {"screen_graph": s0_graph}
        s1 = {"screen_graph": s1_graph}

        params = {"expect_text_present": "Success Banner"}
        res = {"success": True}

        with patch.object(VerificationEngine, "execute_rollback_chain", return_value={"success": True, "message": "rolled back"}) as mock_rollback:
            report = VerificationEngine.post_execute_action(
                agent="Browser",
                action="BROWSER_CLICK",
                params=params,
                res=res,
                s0=s0,
                s1=s1,
                state={"task_graph": {}}
            )

            # Verification should fail and recommend REPLAN
            assert report["success"] is False
            assert report["outcome"] == "FAILURE"
            assert report["recovery_action"] == "REPLAN"
            mock_rollback.assert_called_once()
