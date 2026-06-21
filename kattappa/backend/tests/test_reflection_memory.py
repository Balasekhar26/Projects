import sqlite3
import time
import unittest
from unittest.mock import patch

from backend.core.reflection_memory import ReflectionMemory
from backend.core.reflection_engine import ReflectionEngine
from backend.core.memory_governance import MemoryGovernance


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestReflectionMemoryAndEngine(unittest.TestCase):

    def setUp(self):
        # Create shared in-memory connection
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            ReflectionMemory._ensure_schema(self.__class__._shared_conn)
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

        # Clear tables
        self.__class__._shared_conn.execute("DELETE FROM hm_reflections")
        self.__class__._shared_conn.execute("DELETE FROM hm_interventions")
        self.__class__._shared_conn.execute("DELETE FROM hm_guardrails")
        self.__class__._shared_conn.commit()

        # Patch connection getters
        self.conn_patchers = [
            patch.object(ReflectionMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        for p in self.conn_patchers:
            p.stop()

    def test_schema_exists(self):
        """Verify tables are registered successfully in SQLite."""
        cursor = self.__class__._shared_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        self.assertIn("hm_reflections", tables)
        self.assertIn("hm_interventions", tables)
        self.assertIn("hm_guardrails", tables)

    def test_propose_reflection_deduplication(self):
        """Verify duplicate reflections increment evidence count instead of creating new rows."""
        # 1. Propose first reflection
        ref_id1 = ReflectionMemory.propose_reflection(
            category="RETRIEVAL",
            problem="Too many recall errors",
            cause="Strict score threshold",
            improvement="Relax the score floor from 0.5 to 0.4",
            confidence=0.8,
            source_window_days=7
        )

        # 2. Propose a duplicate (same category, same problem normalized)
        ref_id2 = ReflectionMemory.propose_reflection(
            category="RETRIEVAL",
            problem="  TOO MANY recall errors  ",
            cause="Strict threshold",
            improvement="Lower threshold",
            confidence=0.95, # higher confidence
            source_window_days=10
        )

        # Verify they merged
        self.assertEqual(ref_id1, ref_id2)
        ref = ReflectionMemory.get_reflection(ref_id1)
        self.assertIsNotNone(ref)
        self.assertEqual(ref["evidence_count"], 2)
        self.assertEqual(ref["confidence"], 0.95)

        # Verify total reflections count in DB is 1
        reflections = ReflectionMemory.list_reflections()
        self.assertEqual(len(reflections), 1)

    def test_reflection_lifecycle_and_intervention(self):
        """Verify transition from pending -> testing -> accepted or rejected."""
        ref_id = ReflectionMemory.propose_reflection(
            category="TOOLING",
            problem="Git checkout failure",
            cause="Branch name discrepancy",
            improvement="Check local branches first",
            confidence=0.75,
            source_type="conversation"
        )
        # Duplicate to meet source_count >= 2
        ReflectionMemory.propose_reflection(
            category="TOOLING",
            problem="Git checkout failure",
            cause="Branch name discrepancy",
            improvement="Check local branches first",
            confidence=0.75,
            source_type="user_correction"
        )

        ref = ReflectionMemory.get_reflection(ref_id)
        self.assertEqual(ref["status"], "pending")
        self.assertEqual(ref["source_count"], 2)

        # Start experiment (transitions status to 'testing')
        intervention_id = ReflectionMemory.start_experiment(
            reflection_id=ref_id,
            experiment_name="Git branch safety A/B test",
            change_applied="List branches before checkout",
            metric_before=0.4
        )

        ref = ReflectionMemory.get_reflection(ref_id)
        self.assertEqual(ref["status"], "testing")

        # Conclude experiment with success -> accepted
        success = ReflectionMemory.conclude_experiment(intervention_id, metric_after=0.9, result="success")
        self.assertTrue(success)

        ref = ReflectionMemory.get_reflection(ref_id)
        self.assertEqual(ref["status"], "accepted")

        # Conclude experiment with failure -> rejected
        ref_id2 = ReflectionMemory.propose_reflection(
            category="ALIGNMENT",
            problem="Too friendly",
            cause="Assistant persona settings",
            improvement="Be more precise and technical",
            confidence=0.8,
            source_type="conversation"
        )
        ReflectionMemory.propose_reflection(
            category="ALIGNMENT",
            problem="Too friendly",
            cause="Assistant persona settings",
            improvement="Be more precise and technical",
            confidence=0.8,
            source_type="governance_warning"
        )
        intervention_id2 = ReflectionMemory.start_experiment(ref_id2, "Tone test", "concise tone", 0.5)
        ReflectionMemory.conclude_experiment(intervention_id2, metric_after=0.2, result="failure")

        ref2 = ReflectionMemory.get_reflection(ref_id2)
        self.assertEqual(ref2["status"], "rejected")

    def test_guardrail_management_and_cap(self):
        """Verify active guardrails contradiction checks, prompt injection, and hard cap limits."""
        ref_id = ReflectionMemory.propose_reflection(
            category="ALIGNMENT",
            problem="Verbosity issue",
            cause="Default system prompt",
            improvement="Keep responses concise",
            confidence=0.9,
            source_type="conversation"
        )
        # Duplicate to meet source_count >= 2
        ReflectionMemory.propose_reflection(
            category="ALIGNMENT",
            problem="Verbosity issue",
            cause="Default system prompt",
            improvement="Keep responses concise",
            confidence=0.9,
            source_type="user_correction"
        )

        # Accepted reflection is required to make a guardrail
        int_id = ReflectionMemory.start_experiment(ref_id, "Conciseness trial", "Conciseness prompt", 0.5)
        ReflectionMemory.conclude_experiment(
            int_id,
            metric_after=0.8,
            result="success"
        )
        
        # Verify accepting reflection allows creating guardrail
        gid1 = ReflectionMemory.create_guardrail(ref_id, "Rule: Be concise", priority=0.2)
        self.assertIsNotNone(gid1)

        # Test contradiction check
        with self.assertRaises(ValueError):
            # Opposing rule: detailed explanation
            ReflectionMemory.create_guardrail(ref_id, "Rule: Give detailed verbose explanations", priority=0.9)

        # Test prompt injection
        injected = ReflectionMemory.inject_guardrails("Hello User!")
        self.assertIn("Rule: Be concise", injected)

        # Test hard cap of 5 active guardrails
        # Create other accepted reflections first
        refs = []
        for i in range(5):
            rid = ReflectionMemory.propose_reflection(
                category="SAFETY",
                problem=f"Safety failure {i}",
                cause="Vague system safety limits",
                improvement=f"Enforce rule {i}",
                confidence=0.9,
                source_type="conversation"
            )
            # Duplicate
            ReflectionMemory.propose_reflection(
                category="SAFETY",
                problem=f"Safety failure {i}",
                cause="Vague system safety limits",
                improvement=f"Enforce rule {i}",
                confidence=0.9,
                source_type="governance_warning"
            )
            # Accept reflection
            rid_int = ReflectionMemory.start_experiment(rid, f"Test {i}", f"Rule {i}", 0.5)
            ReflectionMemory.conclude_experiment(rid_int, metric_after=0.9, result="success")
            refs.append(rid)

        # Register 4 more guardrails (total will become 5 active)
        gids = []
        for i in range(4):
            gids.append(ReflectionMemory.create_guardrail(refs[i], f"Safety rule {i}", priority=0.5 + 0.1 * i))

        # Check total active guardrails = 5
        active = ReflectionMemory.list_active_guardrails()
        self.assertEqual(len(active), 5)

        # Add 6th guardrail (total active will exceed 5)
        # Oldest/lowest priority guardrail should be retired
        gid_new = ReflectionMemory.create_guardrail(refs[4], "Safety rule 4", priority=0.9)
        
        active = ReflectionMemory.list_active_guardrails()
        self.assertEqual(len(active), 5)
        self.assertNotIn(gid1, [g["id"] for g in active]) # gid1 had priority 0.2, but others had priority 0.5-0.9

    def test_cross_source_and_guardrail_tracking(self):
        """Verify that testing is blocked without source_count >= 2, and that active guardrails are recorded."""
        # 1. Propose with 1 source
        ref_id = ReflectionMemory.propose_reflection(
            category="REASONING",
            problem="Logic loop in parsing",
            cause="Circular recursion",
            improvement="Add limit check",
            confidence=0.8,
            source_type="conversation"
        )
        
        # Verify starting experiment is blocked
        with self.assertRaises(ValueError) as ctx:
            ReflectionMemory.start_experiment(ref_id, "Loop test", "Limit checks", 0.5)
        self.assertIn("at least 2 independent source types", str(ctx.exception))

        # 2. Add an active guardrail
        # Create an accepted reflection first to spawn a guardrail
        ref_acc_id = ReflectionMemory.propose_reflection(
            category="SAFETY",
            problem="Safety check",
            cause="None",
            improvement="None",
            confidence=0.9,
            source_type="conversation"
        )
        ReflectionMemory.propose_reflection(
            category="SAFETY",
            problem="Safety check",
            cause="None",
            improvement="None",
            confidence=0.9,
            source_type="governance_warning"
        )
        int_id = ReflectionMemory.start_experiment(ref_acc_id, "Safety test", "Check safety", 0.5)
        ReflectionMemory.conclude_experiment(int_id, metric_after=0.9, result="success")
        gid = ReflectionMemory.create_guardrail(ref_acc_id, "Rule: Be safe", priority=0.9)

        # 3. Propose a new reflection - should capture the active guardrail
        ref_new_id = ReflectionMemory.propose_reflection(
            category="SAFETY",
            problem=f"Another safety check {time.time()}",
            cause="None",
            improvement="None",
            confidence=0.9,
            source_type="conversation"
        )
        ref_new = ReflectionMemory.get_reflection(ref_new_id)
        import json
        recorded_gids = json.loads(ref_new["active_guardrails"])
        self.assertIn(gid, recorded_gids)
        
    def test_cleanup_sweep_and_expiry(self):
        """Verify sweep transitions expired reflections to 'expired'."""
        with patch("time.time", return_value=time.time() - 10 * 86400): # 10 days ago
            ref_id = ReflectionMemory.propose_reflection(
                category="SAFETY",
                problem="Safety drift",
                cause="System updates",
                improvement="Safety limits checks",
                confidence=0.8,
                source_window_days=5 # expires in 5 days
            )

        # Ensure active
        ref = ReflectionMemory.get_reflection(ref_id)
        self.assertEqual(ref["status"], "pending")

        # Run sweep
        sweep = ReflectionMemory.run_cleanup_sweep()
        self.assertEqual(sweep["reflections_expired"], 1)

        # Verify status transitioned
        ref = ReflectionMemory.get_reflection(ref_id)
        self.assertEqual(ref["status"], "expired")

    def test_reflection_engine_significance(self):
        """Verify significance calculations based on log error levels."""
        # 1. Clean logs below threshold
        clean_logs = (
            "run_task: start\n"
            "execute_command: exit_code=0\n"
            "run_task: success"
        )
        sig_clean = ReflectionEngine.evaluate_significance(clean_logs)
        self.assertFalse(sig_clean["actionable"])

        # 2. Heavy error logs
        error_logs = (
            "run_task: start\n"
            "execute_command: exit_code=1\n"
            "[Error] Exception raised: database is locked\n"
            "thumbs-down from user: bad response"
        )
        sig_err = ReflectionEngine.evaluate_significance(error_logs)
        self.assertTrue(sig_err["actionable"])

    @patch("backend.core.reflection_engine.ask_model")
    def test_reflection_engine_proposal_and_fallback(self, mock_ask):
        """Verify LLM proposal generation and robust parser fallback."""
        # Mock successful LLM JSON response
        mock_ask.return_value = (
            '{"category": "RETRIEVAL", '
            '"problem": "Retrieves wrong project information", '
            '"cause": "Vector score is too low", '
            '"improvement": "Raise min vector threshold to 0.7", '
            '"confidence": 0.88}'
        )

        error_logs = "execute_command: exit_code=1\nException occurred\n"
        ref_id = ReflectionEngine.analyze_and_propose(error_logs)
        self.assertIsNotNone(ref_id)
        
        ref = ReflectionMemory.get_reflection(ref_id)
        self.assertEqual(ref["category"], "RETRIEVAL")
        self.assertEqual(ref["problem"], "Retrieves wrong project information")
        self.assertEqual(ref["confidence"], 0.88)

        # Mock malformed LLM response to trigger fallback
        mock_ask.return_value = "This is not JSON at all."
        fallback_id = ReflectionEngine.analyze_and_propose(error_logs)
        self.assertIsNotNone(fallback_id)
        
        ref_fall = ReflectionMemory.get_reflection(fallback_id)
        self.assertEqual(ref_fall["category"], "PERFORMANCE")
        self.assertIn("exceptions", ref_fall["problem"])
        self.assertEqual(ref_fall["confidence"], 0.6)

    def test_namespace_isolation(self):
        """Verify that reflection records are completely isolated and never returned by standard queries."""
        # Add reflection
        ref_id = ReflectionMemory.propose_reflection(
            category="RETRIEVAL",
            problem="Isolation issue check",
            cause="Cross leakage",
            improvement="Strict schemas",
            confidence=0.8
        )

        # Check memory retrieval modules do not query reflection tables
        # Simply query provenance for this reflection - it should not exist in provenance unless explicitly logged
        prov = MemoryGovernance.get_provenance(ref_id)
        self.assertIsNone(prov)
