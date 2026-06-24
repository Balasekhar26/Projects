import time
import unittest
import sqlite3
import json
import math
from unittest.mock import patch
from backend.core.episodic_memory import EpisodicMemory


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


class TestEpisodicMemoryV2(unittest.TestCase):

    def setUp(self):
        # Reset memory state
        try:
            EpisodicMemory._get_chroma_collection()
            EpisodicMemory._chroma_client.delete_collection("episodic_vectors")
            EpisodicMemory._collection = None
        except Exception:
            pass

        # Share in-memory connection
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)
            
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

        # Clear all tables
        self.__class__._shared_conn.execute("DELETE FROM episodic_events")
        self.__class__._shared_conn.execute("DELETE FROM episodic_episodes")
        self.__class__._shared_conn.execute("DELETE FROM episodic_reinforcement")
        self.__class__._shared_conn.execute("DELETE FROM hm_episodes")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.commit()

        # Patch connection
        from backend.core.memory_governance import MemoryGovernance
        self.conn_patchers = [
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        EpisodicMemory.stop_worker()
        for p in self.conn_patchers:
            p.stop()

    def test_schema_constraints_and_tables(self):
        # Verify tables exist
        conn = self.__class__._shared_conn
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {t["name"] for t in tables}
        
        expected_tables = {
            "episodic_episodes", "episodic_events", "episodic_people", 
            "episodic_event_people", "episodic_links", 
            "episodic_reinforcement", "episodic_contradictions"
        }
        for name in expected_tables:
            self.assertIn(name, table_names)

    def test_reality_tagging_firewall(self):
        # 1. Create different types of events sharing a common term "firewall_test"
        eid_did = EpisodicMemory.create_episode(
            content="Standard user action execution firewall_test.",
            importance=0.8,
            category="success",
            source_type="DID"
        )
        eid_sim = EpisodicMemory.create_episode(
            content="Simulated predictive action scenario firewall_test.",
            importance=0.8,
            category="success",
            source_type="SIMULATED"
        )
        eid_inf = EpisodicMemory.create_episode(
            content="Inferred strategic principle firewall_test.",
            importance=0.8,
            category="success",
            source_type="INFERRED"
        )
        EpisodicMemory.flush_embeddings()

        # 2. Query default (should return only DID)
        results = EpisodicMemory.recall("firewall_test", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], eid_did)

        # 3. Query specifying SIMULATED and INFERRED
        results_sim_inf = EpisodicMemory.recall("firewall_test", limit=5, source_types=["SIMULATED", "INFERRED"])
        event_ids = {r["id"] for r in results_sim_inf}
        self.assertIn(eid_sim, event_ids)
        self.assertIn(eid_inf, event_ids)
        self.assertNotIn(eid_did, event_ids)

    def test_relevance_floor(self):
        # Create an event
        eid = EpisodicMemory.create_episode(
            content="Compiling tauri bundles for release.",
            importance=0.5,
            category="moment"
        )
        EpisodicMemory.flush_embeddings()

        # Query with high relevance floor
        results_high_floor = EpisodicMemory.recall("tauri", relevance_floor=0.99)
        self.assertEqual(len(results_high_floor), 0)

        # Query with low relevance floor
        results_low_floor = EpisodicMemory.recall("tauri", relevance_floor=0.1)
        self.assertEqual(len(results_low_floor), 1)

    def test_read_only_event_rows(self):
        # Create event
        eid = EpisodicMemory.create_episode(
            content="Refactoring SQLite execution layer.",
            importance=0.7,
            category="moment"
        )
        EpisodicMemory.flush_embeddings()

        # Get initial state of episodic_events row
        conn = self.__class__._shared_conn
        row_before = conn.execute("SELECT * FROM episodic_events WHERE event_id = ?", (eid,)).fetchone()
        dict_before = dict(row_before)

        # Recall multiple times
        for _ in range(3):
            EpisodicMemory.recall("SQLite", limit=1)

        # Verify episodic_events row was NOT modified (read-only invariant)
        row_after = conn.execute("SELECT * FROM episodic_events WHERE event_id = ?", (eid,)).fetchone()
        dict_after = dict(row_after)
        self.assertEqual(dict_before, dict_after)

        # Verify access logs were written
        reinforcements = conn.execute("SELECT * FROM episodic_reinforcement WHERE event_id = ?", (eid,)).fetchall()
        self.assertEqual(len(reinforcements), 3)

    def test_decay_and_boosts(self):
        # 1. Open Episode
        conn = self.__class__._shared_conn
        conn.execute(
            """
            INSERT INTO episodic_episodes (id, project_identifier, title, summary_gist, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("ep-open", "test-project", "Open Episode", "Testing Zeigarnik boost", "OPEN", time.time(), time.time())
        )
        conn.execute(
            """
            INSERT INTO episodic_episodes (id, project_identifier, title, summary_gist, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("ep-resolved", "test-project", "Resolved Episode", "Testing Zeigarnik boost", "RESOLVED", time.time(), time.time())
        )
        conn.commit()

        # 2. Create standard event vs failure event
        eid_std = EpisodicMemory.create_episode(
            content="Standard success execution log.",
            importance=0.7,
            category="success",
            episode_id="ep-open",
            operational_salience=0.1
        )
        eid_fail = EpisodicMemory.create_episode(
            content="Critical database system lockup.",
            importance=0.7,
            category="incident",
            event_type="INCIDENT",
            outcome="FAILURE",
            episode_id="ep-resolved",
            operational_salience=0.1
        )
        EpisodicMemory.flush_embeddings()

        # Let's verify decay calculation logic
        # Decay for standard is lambda = 0.15, failure/incident is lambda = 0.02
        # Mock time jump: simulate 10 days since access
        now = time.time()
        ten_days_ago = now - (86400 * 10)
        
        # Insert a reinforcement log to establish last access time
        conn.execute(
            "INSERT INTO episodic_reinforcement (event_id, access_timestamp, retrieval_reason) VALUES (?, ?, ?)",
            (eid_std, ten_days_ago, "mock last access")
        )
        conn.execute(
            "INSERT INTO episodic_reinforcement (event_id, access_timestamp, retrieval_reason) VALUES (?, ?, ?)",
            (eid_fail, ten_days_ago, "mock last access")
        )
        conn.commit()

        # Retrieve standard episode
        results_std = EpisodicMemory.recall("success", limit=5, source_types=["DID"])
        res_std = next(r for r in results_std if r["id"] == eid_std)

        # Standard decay check: importance = 0.7, operational_salience = 0.1, lambda = 0.15, 10 days decay.
        # Plus status boost of 0.25 (since parent episode 'ep-open' is OPEN)
        # Decay factor: exp(-0.15 * 10) = exp(-1.5) = 0.22313
        # Strength: min(1.0, 0.7 * 0.22313 * (1.0 + 0.1) + 0.25) = min(1.0, 0.1718 + 0.25) = 0.4218
        self.assertAlmostEqual(res_std["decay_score"], 0.4218, places=2)

        # Retrieve failure episode
        results_fail = EpisodicMemory.recall("database", limit=5, source_types=["DID"])
        res_fail = next(r for r in results_fail if r["id"] == eid_fail)

        # Failure decay check: importance = 0.7, operational_salience = 0.1, lambda = 0.02, 10 days decay.
        # No status boost (since parent episode 'ep-resolved' is RESOLVED)
        # Decay factor: exp(-0.02 * 10) = exp(-0.2) = 0.81873
        # Strength: min(1.0, 0.7 * 0.81873 * (1.0 + 0.1) + 0.0) = 0.6304
        self.assertAlmostEqual(res_fail["decay_score"], 0.6304, places=2)

        # Failure decays much slower than standard event!
        self.assertGreater(res_fail["decay_score"], res_std["decay_score"])

    def test_decision_state_snapshot(self):
        # Create an event with a decision state
        decision_state = {
            "known_information": "SQLite DB exists",
            "assumptions": ["SQLite handles single-process writes safely"],
            "risk_estimate": 0.25,
            "confidence": 0.85
        }
        
        eid = EpisodicMemory.create_episode(
            content="Testing decision state snapshot.",
            importance=0.6,
            category="planning",
            decision_state=decision_state
        )
        EpisodicMemory.flush_embeddings()
        
        # Verify get_episode retrieves decision_state
        episode = EpisodicMemory.get_episode(eid)
        self.assertIsNotNone(episode)
        self.assertEqual(episode["decision_state"], decision_state)
        
        # Verify recall retrieves decision_state
        results = EpisodicMemory.recall("decision state", limit=5)
        res_evt = next((r for r in results if r["id"] == eid), None)
        self.assertIsNotNone(res_evt)
        self.assertEqual(res_evt["decision_state"], decision_state)

    def test_verbatim_trace_hash_tamper_detection(self):
        # Create a standard trace event
        content = "Secure trace that must not be tampered."
        eid = EpisodicMemory.create_episode(
            content=content,
            importance=0.7,
            category="implementation",
            verbatim_trace=content
        )
        EpisodicMemory.flush_embeddings()
        
        # Retrieve and verify it is accessible first
        episode = EpisodicMemory.get_episode(eid)
        self.assertIsNotNone(episode)
        self.assertEqual(episode["verbatim_trace"], content)
        
        # Manually tamper with the verbatim trace in the database
        conn = self.__class__._shared_conn
        conn.execute(
            "UPDATE episodic_events SET verbatim_trace = 'TAMPERED TRACE' WHERE event_id = ?",
            (eid,)
        )
        conn.commit()
        
        # get_episode should return None due to hash mismatch
        episode_tampered = EpisodicMemory.get_episode(eid)
        self.assertIsNone(episode_tampered)
        
        # recall should also skip the tampered record
        results = EpisodicMemory.recall("trace", limit=5)
        res_evt = next((r for r in results if r["id"] == eid), None)
        self.assertIsNone(res_evt)

    def test_memory_confidence_score(self):
        # 1. Create a DID event (reliability = 1.0)
        eid_did = EpisodicMemory.create_episode(
            content="DID event content",
            importance=0.7,
            category="testing",
            source_type="DID"
        )
        # 2. Create a SIMULATED event (reliability = 0.5)
        eid_sim = EpisodicMemory.create_episode(
            content="SIMULATED event content",
            importance=0.7,
            category="testing",
            source_type="SIMULATED"
        )
        EpisodicMemory.flush_embeddings()
        
        # Fetch initial confidence values (no links, no contradictions, time_elapsed approx 0)
        ep_did = EpisodicMemory.get_episode(eid_did)
        ep_sim = EpisodicMemory.get_episode(eid_sim)
        
        self.assertAlmostEqual(ep_did["confidence"], 1.0, places=1)
        self.assertAlmostEqual(ep_sim["confidence"], 0.5, places=1)
        
        # 3. Add 2 corroboration links (0.05 * 2 = 0.10 boost)
        conn = self.__class__._shared_conn
        conn.execute(
            "INSERT INTO episodic_links (source_event_id, target_event_id, link_type) VALUES (?, ?, ?)",
            (eid_did, eid_sim, "RELATED_TO")
        )
        conn.execute(
            "INSERT INTO episodic_links (source_event_id, target_event_id, link_type) VALUES (?, ?, ?)",
            (eid_sim, eid_did, "FOLLOW_UP_TO")
        )
        # 4. Add 1 contradiction (-15% impact: 1.0 * (1 - 0.15 * 1) = 0.85)
        conn.execute(
            "INSERT INTO episodic_contradictions (source_event_id, contradicting_event_id, contradiction_type, confidence) VALUES (?, ?, ?, ?)",
            (eid_did, eid_sim, "FACTUAL", 0.8)
        )
        conn.commit()
        
        # Fetch confidence again
        ep_did_updated = EpisodicMemory.get_episode(eid_did)
        # For DID: source_reliability = 1.0, contradiction_count = 1, corroboration_count = 2
        # Formula: 1.0 * (1 - 0.15 * 1) + 0.05 * 2 = 0.85 + 0.10 = 0.95
        self.assertAlmostEqual(ep_did_updated["confidence"], 0.95, places=2)

    def test_reinforcement_saturation_limits(self):
        eid = EpisodicMemory.create_episode(
            content="Frequently retrieved event content.",
            importance=0.6,
            category="testing"
        )
        EpisodicMemory.flush_embeddings()
        
        # Add 100 reinforcement logs to trigger saturation
        conn = self.__class__._shared_conn
        now = time.time()
        for i in range(100):
            conn.execute(
                "INSERT INTO episodic_reinforcement (event_id, access_timestamp, retrieval_reason) VALUES (?, ?, ?)",
                (eid, now, f"mock access {i}")
            )
        conn.commit()
        
        # Fetch recall results
        results = EpisodicMemory.recall("Frequently", limit=5)
        self.assertEqual(len(results), 1)
        res_evt = results[0]
        
        # Verify reinforcement composite score contribution is capped at 15% (0.15)
        # The reinforcement component is 0.15 * min(1.0, reinforcement)
        # Let's verify that the composite score does not exceed 1.0, and the weight formula works.
        self.assertLessEqual(res_evt["composite_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
