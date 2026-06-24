import time
import unittest
import sqlite3
import json
from unittest.mock import patch
from backend.core.episodic_memory import EpisodicMemory
from backend.core.reflection_memory import ReflectionMemory
from backend.core.strategic_memory import StrategicMemory
from backend.core.reflection_engine import ReflectionEngine


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


class TestReflectionConsolidation(unittest.TestCase):

    def setUp(self):
        # Reset mock database connection
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)
            ReflectionMemory._ensure_schema(self.__class__._shared_conn)
            StrategicMemory._ensure_schema(self.__class__._shared_conn)
            
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

        # Clear tables
        self.__class__._shared_conn.execute("DELETE FROM episodic_events")
        self.__class__._shared_conn.execute("DELETE FROM episodic_episodes")
        self.__class__._shared_conn.execute("DELETE FROM hm_strategic_goals")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.commit()

        # Patch database connections to use the shared in-memory DB
        from backend.core.memory_governance import MemoryGovernance
        self.conn_patchers = [
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(ReflectionMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(StrategicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        EpisodicMemory.stop_worker()
        for p in self.conn_patchers:
            p.stop()

    def test_consolidation_evidence_count_gate(self):
        # Create an episode project
        conn = self.__class__._shared_conn
        conn.execute(
            """
            INSERT INTO episodic_episodes (id, project_identifier, title, summary_gist, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("proj-1", "cache-optimization", "Cache Optimization", "Group of related cache events", "OPEN", time.time(), time.time())
        )
        conn.commit()

        # 1. Create only 2 events for "cache-optimization" (less than minimum evidence count of 3)
        EpisodicMemory.create_episode(
            content="Implement redis cache query.",
            importance=0.8,
            category="implementation",
            outcome="SUCCESS",
            lesson_learned="Redis cache reduces DB query latency.",
            episode_id="proj-1"
        )
        EpisodicMemory.create_episode(
            content="Setup fallback memory cache.",
            importance=0.8,
            category="implementation",
            outcome="SUCCESS",
            lesson_learned="Local cache handles redis timeouts.",
            episode_id="proj-1"
        )
        EpisodicMemory.flush_embeddings()

        # Run consolidation - should promote 0 principles because evidence count = 2 (< 3)
        promoted = ReflectionEngine.consolidate_episodic_memories()
        self.assertEqual(len(promoted), 0)

        # 2. Add a 3rd event to reach the evidence count gate threshold of 3.
        # However, 3 successes out of 3 total trials has a Wilson lower bound of ~0.4385, which is < 0.50.
        # So it should STILL not promote because it fails the Wilson score interval gate.
        EpisodicMemory.create_episode(
            content="Verify cache eviction strategy.",
            importance=0.8,
            category="testing",
            outcome="SUCCESS",
            lesson_learned="Least-recently-used cache prevents OOM.",
            episode_id="proj-1"
        )
        EpisodicMemory.flush_embeddings()

        promoted_3 = ReflectionEngine.consolidate_episodic_memories()
        self.assertEqual(len(promoted_3), 0)

        # 3. Add a 4th event (4 successes out of 4 total trials has a Wilson lower bound of ~0.5101, which is >= 0.50).
        # This should successfully promote.
        EpisodicMemory.create_episode(
            content="Profile cache serialization speed.",
            importance=0.8,
            category="testing",
            outcome="SUCCESS",
            lesson_learned="JSON serialization outperforms pickle for simple objects.",
            episode_id="proj-1"
        )
        EpisodicMemory.flush_embeddings()

        promoted_4 = ReflectionEngine.consolidate_episodic_memories()
        self.assertEqual(len(promoted_4), 1)

        # Verify the promoted strategic goal
        goal_id = promoted_4[0]
        goal_row = conn.execute("SELECT * FROM hm_strategic_goals WHERE id = ?", (goal_id,)).fetchone()
        self.assertIsNotNone(goal_row)
        self.assertEqual(goal_row["status"], "draft")
        self.assertEqual(goal_row["trust_level"], "TRUST_UNVERIFIED")
        self.assertEqual(goal_row["approved_by_user"], 0)
        self.assertIn("INFERRED", goal_row["goal"])

    def test_wilson_score_gate(self):
        # Create an episode project
        conn = self.__class__._shared_conn
        conn.execute(
            """
            INSERT INTO episodic_episodes (id, project_identifier, title, summary_gist, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("proj-2", "db-indexing", "DB Indexing", "Grouping related index trials", "OPEN", time.time(), time.time())
        )
        conn.commit()

        # Create 3 events, but let's make 2 of them failures (success rate = 1/3 = 33%).
        # This will fail the Wilson score lower bound check (since Lower Bound of 1/3 is far below 0.50).
        EpisodicMemory.create_episode(
            content="Create composite index on users.",
            importance=0.8,
            category="implementation",
            outcome="SUCCESS",
            lesson_learned="Composite index speeds up user search.",
            episode_id="proj-2"
        )
        EpisodicMemory.create_episode(
            content="Create bad index on text field.",
            importance=0.8,
            category="implementation",
            outcome="FAILURE",
            lesson_learned="Large text indexing slows down writes.",
            episode_id="proj-2"
        )
        EpisodicMemory.create_episode(
            content="Add index during heavy transactions.",
            importance=0.8,
            category="implementation",
            outcome="FAILURE",
            lesson_learned="Indexing during load locks the database.",
            episode_id="proj-2"
        )
        EpisodicMemory.flush_embeddings()

        # Run consolidation - should promote 0 due to low success rate
        promoted = ReflectionEngine.consolidate_episodic_memories()
        self.assertEqual(len(promoted), 0)

    def test_consolidation_rate_limit(self):
        # Test that no more than 5 strategic promotions are created per day
        conn = self.__class__._shared_conn
        
        # Insert 6 different projects to satisfy evidence counts
        for i in range(6):
            proj_id = f"proj-{i}"
            conn.execute(
                """
                INSERT INTO episodic_episodes (id, project_identifier, title, summary_gist, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (proj_id, f"project-{i}", f"Project {i}", "Gist", "OPEN", time.time(), time.time())
            )
            # Add 4 successful events for each project to satisfy Wilson Score (lower bound >= 0.50) & Evidence Count
            for j in range(4):
                EpisodicMemory.create_episode(
                    content=f"Event {i}-{j} execution.",
                    importance=0.9,
                    category="implementation",
                    outcome="SUCCESS",
                    lesson_learned=f"Lesson learned from project {i}.",
                    episode_id=proj_id
                )
        EpisodicMemory.flush_embeddings()

        # Run consolidation - should promote at most 5 principles because max_promotions_per_day = 5
        promoted = ReflectionEngine.consolidate_episodic_memories()
        self.assertLessEqual(len(promoted), 5)


if __name__ == "__main__":
    unittest.main()
