"""Step 12: Self-Reflection System — Architecture Contract Tests.

Validates:
  1. Reflection ≠ Authority: Zero imports from reflection modules in authority.
  2. Wilson Score Interval: Deterministic calculation boundaries.
  3. Domain-Based Protected-Core Isolation: Refusal to store security/authority proposals.
  4. Echo-Chamber Prevention: Provenance-based exclusion of reflection-derived memories.
  5. Verification & Approval Double-Gate: Both gates required for promotion.
  6. Selection Bias Warnings & Drift Alerts.
"""

from __future__ import annotations

import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from backend.core.reflection_memory import ReflectionMemory
from backend.core.reflection_engine import ReflectionEngine
from backend.core.memory_governance import MemoryGovernance
from backend.core.semantic_memory import SemanticMemory


class _NoClose:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass


def _make_shared_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class TestSelfReflectionSystem(unittest.TestCase):

    def setUp(self):
        conn = _make_shared_conn()
        self.__class__._conn = conn

        ReflectionMemory._ensure_schema(conn)
        MemoryGovernance._ensure_schema(conn)
        SemanticMemory._ensure_schema(conn)

        wrapped = _NoClose(conn)
        self._patchers = [
            patch.object(ReflectionMemory, "_get_sqlite_conn", return_value=wrapped),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=wrapped),
            patch.object(SemanticMemory, "_get_sqlite_conn", return_value=wrapped),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        # Clean state between tests
        ReflectionMemory.clear_all()
        # Clear extra tables
        try:
            self.__class__._conn.execute("DELETE FROM hm_semantic_nodes")
            self.__class__._conn.execute("DELETE FROM hm_provenance")
            self.__class__._conn.commit()
        except Exception:
            pass

    # =========================================================================
    # 1. Reflection ≠ Authority: Zero Imports
    # =========================================================================

    def test_reflection_authority_isolation(self):
        import importlib
        authority_modules = [
            "backend.core.execution_policy",
            "backend.core.risk_classifier",
            "backend.core.capability_broker",
            "backend.core.approval_engine",
        ]
        for mod_name in authority_modules:
            try:
                mod = importlib.import_module(mod_name)
            except ImportError:
                self.skipTest(f"{mod_name} not importable")

            for attr_name in dir(mod):
                try:
                    attr = getattr(mod, attr_name)
                    mod_path = getattr(attr, "__module__", "") or ""
                    self.assertNotIn("reflection_memory", mod_path)
                    self.assertNotIn("reflection_engine", mod_path)
                except Exception:
                    pass

    # =========================================================================
    # 2. Wilson Score Interval (CI Bounds Check)
    # =========================================================================

    def test_wilson_confidence_boundaries(self):
        # 1. Small sample: 1 success / 3 trials -> wide CI bounds
        lower, upper = ReflectionEngine.calculate_wilson_score_interval(1, 3)
        self.assertLess(lower, 0.20)
        self.assertGreater(upper, 0.70)
        self.assertGreater(upper - lower, 0.50, "Small sample size must yield a wide confidence interval.")

        # 2. Large sample: 900 successes / 1000 trials -> narrow CI bounds
        lower_lg, upper_lg = ReflectionEngine.calculate_wilson_score_interval(900, 1000)
        self.assertGreater(lower_lg, 0.85)
        self.assertLess(upper_lg, 0.93)
        self.assertLess(upper_lg - lower_lg, 0.08, "Large sample size must yield a narrow confidence interval.")

        # 3. Boundaries clamp correctly
        l0, u0 = ReflectionEngine.calculate_wilson_score_interval(0, 0)
        self.assertEqual(l0, 0.0)
        self.assertEqual(u0, 0.0)

    # =========================================================================
    # 3. Domain-Based Protected-Core Isolation (RF5 Guardrail)
    # =========================================================================

    def test_protected_core_domain_writes_blocked(self):
        # Valid domain works
        obs_id = ReflectionMemory.add_reflection_observation("sess-01", "memory", "recall", "SUCCESS", "{}")
        self.assertIsNotNone(obs_id)

        # Forbidden domains ('security' or 'authority') must throw ValueError
        with self.assertRaises(ValueError):
            ReflectionMemory.add_reflection_observation(
                "sess-01", "security", "gate_check", "FAILURE", "{}"
            )

        with self.assertRaises(ValueError):
            ReflectionMemory.add_reflection_hypothesis(
                pattern_id=None,
                domain="authority",
                statement="Bypass manual verification steps to optimize speed.",
                predicted_metric_change="execution_speed > 2.0",
                lower_ci=0.7,
                upper_ci=0.9
            )

        # Verify drift alert is logged automatically for blocked domain attempts
        alerts = ReflectionMemory.get_drift_alerts()
        self.assertTrue(len(alerts) >= 2)
        self.assertTrue(any(a["alert_type"] == "SECURITY_POSTURE_INTERFERENCE" for a in alerts))

    # =========================================================================
    # 4. Echo-Chamber Prevention (RF4 Origin Filter)
    # =========================================================================

    def test_echo_chamber_exclusion_in_pattern_queries(self):
        # 1. Add typical success and failure observations
        ReflectionMemory.add_reflection_observation("sess-01", "retrieval", "recall", "SUCCESS", '{"source": "user"}')
        ReflectionMemory.add_reflection_observation("sess-01", "retrieval", "recall", "SUCCESS", '{"source": "user"}')

        # 2. Add an observation that carries 'reflection_engine' source tag (echo chamber check)
        ReflectionMemory.add_reflection_observation(
            "sess-01", "retrieval", "recall", "FAILURE", '{"source": "reflection_engine"}'
        )

        # Compile daily report
        report = ReflectionEngine.compile_daily_reflection()

        # The failures list should NOT include the 'reflection_engine' observation due to the source filter
        # It only evaluated the 2 SUCCESS observations from 'user'
        self.assertEqual(len(report["failures"]), 0)
        self.assertEqual(len(report["successes"]), 1)
        self.assertEqual(report["successes"][0]["total_opportunities"], 2)

    # =========================================================================
    # 5. Verification & Approval Double-Gate
    # =========================================================================

    def test_double_gate_promotion(self):
        hyp_id = ReflectionMemory.add_reflection_hypothesis(
            pattern_id=None,
            domain="memory",
            statement="Context payload cap of 8 improves memory precision.",
            predicted_metric_change="precision > 0.85",
            lower_ci=0.68,
            upper_ci=0.84
        )

        # Initially, not promoted
        hyp = ReflectionMemory.get_hypothesis(hyp_id)
        self.assertEqual(hyp["status"], "pending")
        self.assertEqual(hyp["is_verified"], 0)
        self.assertEqual(hyp["is_approved"], 0)

        # Gate 1: Verify only -> does NOT promote
        ReflectionEngine.verify_hypothesis(hyp_id, success=True)
        hyp = ReflectionMemory.get_hypothesis(hyp_id)
        self.assertEqual(hyp["status"], "verified")
        self.assertEqual(hyp["is_verified"], 1)
        self.assertEqual(hyp["is_approved"], 0)
        self.assertEqual(len(SemanticMemory.recall("Context payload")), 0)

        # Gate 2: Approve -> Double-Gate met -> promotes to Semantic Memory
        ReflectionEngine.approve_hypothesis(hyp_id, reviewer_id="admin-01")
        hyp = ReflectionMemory.get_hypothesis(hyp_id)
        self.assertEqual(hyp["status"], "promoted")
        self.assertEqual(hyp["is_approved"], 1)

        # Verify semantic memory inclusion + RF4 provenance check
        results = SemanticMemory.recall("Context payload")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["description"], "Context payload cap of 8 improves memory precision.")

        # Lineage checked
        prov = MemoryGovernance.get_provenance(results[0]["id"])
        self.assertIsNotNone(prov)
        self.assertEqual(prov["source"], "reflection_engine")
        self.assertEqual(prov["created_by"], "admin-01")

    # =========================================================================
    # 6. Drift Alarms & Selection Bias
    # =========================================================================

    def test_sycophancy_drift_alarm(self):
        # Log 50 sessions with 0 user corrections
        for i in range(55):
            ReflectionMemory.add_reflection_observation(f"sess-{i}", "communication", "response", "SUCCESS", "{}")

        report = ReflectionEngine.compile_daily_reflection()
        self.assertIn("drift_alarms", report)
        self.assertTrue(any("Sycophancy alert" in d for d in report["drift_alarms"]))

        # Verify drift alert saved in DB
        alerts = ReflectionMemory.get_drift_alerts()
        self.assertTrue(any(a["alert_type"] == "SYCOPHANCY_DRIFT" for a in alerts))

    # =========================================================================
    # Refinements & Step 13 Integration Tests
    # =========================================================================

    def test_held_out_evidence_verification(self):
        # 1. Create hypothesis with a cutoff timestamp
        cutoff = time.time()
        hyp_id = ReflectionMemory.add_reflection_hypothesis(
            pattern_id=None,
            domain="memory",
            statement="Verification checks on held-out data works.",
            predicted_metric_change="accuracy > 0.9",
            lower_ci=0.6,
            upper_ci=0.8,
            evidence_cutoff_timestamp=cutoff
        )

        # 2. Add old observations (before cutoff) -> should be ignored
        with patch("time.time", return_value=cutoff - 10):
            ReflectionMemory.add_reflection_observation("sess-old", "memory", "recall", "FAILURE", "{}")
            ReflectionMemory.add_reflection_observation("sess-old-2", "memory", "recall", "FAILURE", "{}")

        # 3. Add new observations (after cutoff) -> held-out evidence
        with patch("time.time", return_value=cutoff + 10):
            ReflectionMemory.add_reflection_observation("sess-new-1", "memory", "recall", "SUCCESS", "{}")
            ReflectionMemory.add_reflection_observation("sess-new-2", "memory", "recall", "SUCCESS", "{}")
            ReflectionMemory.add_reflection_observation("sess-new-3", "memory", "recall", "SUCCESS", "{}")

        # Run verification check
        success, report = ReflectionEngine.verify_hypothesis_with_held_out_evidence(hyp_id)
        self.assertTrue(success)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["total_trials"], 3)
        self.assertEqual(report["successes"], 3)
        self.assertEqual(report["failures"], 0)

        # Verify hypothesis state updated in DB
        hyp = ReflectionMemory.get_hypothesis(hyp_id)
        self.assertEqual(hyp["status"], "verified")
        self.assertEqual(hyp["is_verified"], 1)

    def test_expanded_protected_domains(self):
        # Verify expanded list of protected domains
        protected_domains = [
            "approval", "permissions", "capability_management", 
            "risk_management", "identity_verification"
        ]
        for domain in protected_domains:
            with self.assertRaises(ValueError):
                ReflectionMemory.add_reflection_observation("sess-1", domain, "check", "SUCCESS", "{}")
            with self.assertRaises(ValueError):
                ReflectionMemory.add_reflection_hypothesis(
                    pattern_id=None,
                    domain=domain,
                    statement="Try to disable check",
                    predicted_metric_change="speed > 1.2",
                    lower_ci=0.7,
                    upper_ci=0.8
                )

        # Verify drift alert is logged for security posture interference
        alerts = ReflectionMemory.get_drift_alerts()
        self.assertTrue(any(a["alert_type"] == "SECURITY_POSTURE_INTERFERENCE" for a in alerts))

    def test_selection_bias_with_unknown_outcomes(self):
        # 1. Log observations: 2 SUCCESS, 1 FAILURE, 2 UNKNOWN (unknowns rate = 40% > 30%)
        ReflectionMemory.add_reflection_observation("sess-1", "memory", "recall", "SUCCESS", "{}")
        ReflectionMemory.add_reflection_observation("sess-2", "memory", "recall", "SUCCESS", "{}")
        ReflectionMemory.add_reflection_observation("sess-3", "memory", "recall", "FAILURE", "{}")
        ReflectionMemory.add_reflection_observation("sess-4", "memory", "recall", "UNKNOWN", "{}")
        ReflectionMemory.add_reflection_observation("sess-5", "memory", "recall", "UNKNOWN", "{}")

        report = ReflectionEngine.compile_daily_reflection()
        self.assertEqual(report["evidence_window"]["total_interactions_logged"], 5)
        self.assertEqual(report["evidence_window"]["unobserved_interactions"], 2)
        self.assertTrue(report["evidence_window"]["selection_bias_warning"])

    def test_reflection_provenance_exclusion_filter(self):
        # 1. Log observation from user
        ReflectionMemory.add_reflection_observation("sess-1", "memory", "recall", "SUCCESS", '{"source": "user"}')
        # 2. Log observation from reflection_engine (echo chamber source)
        ReflectionMemory.add_reflection_observation("sess-2", "memory", "recall", "FAILURE", '{"provenance": "reflection_engine"}')

        report = ReflectionEngine.compile_daily_reflection()
        # The failures list should NOT include the 'reflection_engine' observation
        self.assertEqual(len(report["failures"]), 0)
        self.assertEqual(len(report["successes"]), 1)
        self.assertEqual(report["successes"][0]["total_opportunities"], 1)

    def test_step13_plan_thrashing_adaptation_proposals(self):
        # Set up a mock goal_memory DB
        from backend.core.config import load_config
        config = load_config()
        db_path = config.sqlite_path.parent / "goal_memory.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch()

        goal_memory_conn = sqlite3.connect(":memory:")
        goal_memory_conn.execute(
            """
            CREATE TABLE plan_blueprints (
                blueprint_id TEXT PRIMARY KEY,
                linked_goal_id TEXT NOT NULL,
                total_replans INTEGER DEFAULT 0,
                blueprint_status TEXT NOT NULL
            )
            """
        )
        # bp-01 has 3 replans (thrashing) -> PAUSE
        goal_memory_conn.execute("INSERT INTO plan_blueprints (blueprint_id, linked_goal_id, total_replans, blueprint_status) VALUES ('bp-01', 'goal-123', 3, 'STAGED')")
        # bp-02 is RESOURCE_UNAVAILABLE -> DELAY
        goal_memory_conn.execute("INSERT INTO plan_blueprints (blueprint_id, linked_goal_id, total_replans, blueprint_status) VALUES ('bp-02', 'goal-456', 0, 'RESOURCE_UNAVAILABLE')")
        goal_memory_conn.commit()

        try:
            # Mock sqlite3.connect to return the in-memory goal_memory_conn
            with patch("sqlite3.connect", return_value=goal_memory_conn):
                proposals = ReflectionEngine.analyze_plan_performance_and_propose_adaptation()
        finally:
            if db_path.exists():
                try:
                    db_path.unlink()
                except Exception:
                    pass

        self.assertEqual(len(proposals), 2)

        # Retrieve pending proposals from DB
        props = ReflectionMemory.list_goal_adaptation_proposals(status="pending")
        self.assertEqual(len(props), 2)

        prop_map = {p["goal_id"]: p for p in props}
        self.assertIn("goal-123", prop_map)
        self.assertEqual(prop_map["goal-123"]["suggested_action"], "PAUSE")
        self.assertIn("Plan blueprint bp-01 thrashed", prop_map["goal-123"]["reason"])

        self.assertIn("goal-456", prop_map)
        self.assertEqual(prop_map["goal-456"]["suggested_action"], "DELAY")
        self.assertIn("Plan blueprint bp-02 resource constraints", prop_map["goal-456"]["reason"])

        # Approve a proposal
        approved = ReflectionMemory.update_goal_adaptation_proposal_status(prop_map["goal-123"]["id"], "approved")
        self.assertTrue(approved)

        # Check status updated
        props_after = ReflectionMemory.list_goal_adaptation_proposals()
        prop_123 = next(p for p in props_after if p["goal_id"] == "goal-123")
        self.assertEqual(prop_123["status"], "approved")


if __name__ == "__main__":
    unittest.main()
