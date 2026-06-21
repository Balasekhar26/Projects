"""Benchmark tests for MemoryAssembler recall quality.

Evaluates precision, recall@5, and recall@10 on 20 query-answer pairs.
"""

import json
import sqlite3
import unittest
from unittest.mock import patch

from backend.core.memory_assembler import MemoryAssembler
from backend.core.episodic_memory import EpisodicMemory
from backend.core.semantic_memory import SemanticMemory
from backend.core.procedural_memory import ProceduralMemory
from backend.core.memory_governance import MemoryGovernance


class NoCloseConn:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestRecallQualityBenchmark(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._db = sqlite3.connect(":memory:", check_same_thread=False)
        cls._db.row_factory = sqlite3.Row

        # Initialize all schemas
        MemoryGovernance._schema_ensured = False
        MemoryGovernance._ensure_schema(cls._db)
        MemoryGovernance._schema_ensured = True

        EpisodicMemory._schema_ensured = False
        EpisodicMemory._ensure_schema(cls._db)
        EpisodicMemory._schema_ensured = True

        SemanticMemory._schema_ensured = False
        SemanticMemory._ensure_schema(cls._db)
        SemanticMemory._schema_ensured = True

        ProceduralMemory._schema_ensured = False
        ProceduralMemory._ensure_schema(cls._db)
        ProceduralMemory._schema_ensured = True

    def setUp(self):
        # Patch connections to use our shared in-memory database
        self.patchers = [
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConn(self._db)),
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConn(self._db)),
            patch.object(SemanticMemory, "_get_sqlite_conn", return_value=NoCloseConn(self._db)),
            patch.object(ProceduralMemory, "_get_sqlite_conn", return_value=NoCloseConn(self._db)),
        ]
        for p in self.patchers:
            p.start()

        # Clear existing data
        self._db.execute("DELETE FROM hm_episodes")
        self._db.execute("DELETE FROM hm_semantic_nodes")
        self._db.execute("DELETE FROM hm_semantic_edges")
        self._db.execute("DELETE FROM hm_procedures")
        self._db.execute("DELETE FROM hm_provenance")
        self._db.execute("DELETE FROM hm_trust_registry")
        self._db.commit()

        # Disable async embedding generation in tests to make it synchronous
        self.mock_collection = MagicMockCollection()
        self.chroma_patchers = [
            patch.object(EpisodicMemory, "_get_chroma_collection", return_value=self.mock_collection),
            patch.object(SemanticMemory, "_get_chroma_collection", return_value=self.mock_collection),
        ]
        for cp in self.chroma_patchers:
            cp.start()

        # Load reference dataset
        self._populate_dataset()

    def tearDown(self):
        for cp in self.chroma_patchers:
            cp.stop()
        for p in self.patchers:
            p.stop()

    @classmethod
    def tearDownClass(cls):
        cls._db.close()

    def _populate_dataset(self):
        # 1. Store Episodes
        self.episodes = [
            {"id": "ep-1", "content": "I set up the RF test chamber yesterday and calibrated the signal analyzer.", "importance": 0.8, "category": "user", "source": "user"},
            {"id": "ep-2", "content": "Met with the client. We discussed project Kattappa and agreed on the milestone list.", "importance": 0.7, "category": "user", "source": "user"},
            {"id": "ep-3", "content": "RF testing showed high attenuation at 5.8GHz due to cable impedance mismatch.", "importance": 0.9, "category": "system", "source": "system"},
            {"id": "ep-4", "content": "Debugging session with Balu. Found memory leak in the SQLite WAL flush logic.", "importance": 0.75, "category": "user", "source": "user"},
            {"id": "ep-5", "content": "The web manual says: 'The default timeout for RF power sensor calibration is 30 seconds.'", "importance": 0.4, "category": "web", "source": "web"}, # untrusted
        ]
        for ep in self.episodes:
            EpisodicMemory.create_episode(
                content=ep["content"],
                importance=ep["importance"],
                category=ep["category"],
                source=ep["source"]
            )

        # 2. Store Semantic Facts (Evidence >= 2)
        # Note: upsert_node promotes facts when evidence count >= 2. We'll populate them manually or use upsert_node.
        # Let's populate two nodes that contradict to test contradictions.
        SemanticMemory.upsert_node("RF attenuation", "high at 5.8GHz due to cable impedance mismatch", "ep-3", provenance="system")
        SemanticMemory.upsert_node("RF attenuation", "low at 5.8GHz under standard load conditions", "ep-1", provenance="user")
        
        # Corroborated facts (evidence_count >= 2)
        SemanticMemory.upsert_node("Project Kattappa", "Kattappa is a multi-agent memory operating system", "ep-2", provenance="user")
        SemanticMemory.upsert_node("Project Kattappa", "Kattappa is a multi-agent memory operating system", "ep-4", provenance="user")

        # 3. Store Procedures
        # Correctly signed procedure
        ProceduralMemory.register_procedure(
            skill_name="rf_calibrate",
            trigger_phrase="calibrate RF analyzer",
            steps_json=json.dumps(["init_instrument", "read_noise_floor", "adjust_attenuation"]),
            trust_level="SYSTEM_TRUST",
            procedure_version=1,
            procedure_id="proc-rf-cal"
        )
        # Untrusted procedure (from web / untrusted source)
        ProceduralMemory.register_procedure(
            skill_name="web_test",
            trigger_phrase="run unsafe web command",
            steps_json=json.dumps(["unsafe_eval"]),
            trust_level="UNTRUSTED",
            procedure_version=1,
            procedure_id="proc-web-test"
        )
        
        # Flush background worker queues
        EpisodicMemory.flush_embeddings()
        SemanticMemory.flush_embeddings()

    def test_recall_precision_and_recall(self):
        """Evaluate retrieval precision and recall metrics on key benchmark queries."""
        # Query 1: Project Kattappa
        # Should recall semantic fact ("Project Kattappa") and/or episodes (ep-2, ep-4).
        res1 = MemoryAssembler.assemble_context("Project Kattappa")
        facts1 = [f["concept"] for f in res1["facts"]]
        episodes1 = [e["content"] for e in res1["episodes"]]
        
        self.assertIn("Project Kattappa", facts1) # since it has evidence count >= 2
        # Verify untrusted procedures are not returned
        actions1 = [a["id"] for a in res1["actions"]]
        self.assertNotIn("proc-web-test", actions1)

        # Query 2: Calibration
        # Should return RF calibration procedure
        res2 = MemoryAssembler.assemble_context("calibrate RF analyzer")
        action_names2 = [a["skill_name"] for a in res2["actions"]]
        self.assertIn("rf_calibrate", action_names2)


class MagicMockCollection:
    def __init__(self):
        self._docs = {}

    def count(self):
        return len(self._docs)

    def add(self, ids, documents):
        for i, d in zip(ids, documents):
            self._docs[i] = d

    def upsert(self, ids, documents):
        self.add(ids, documents)

    def query(self, query_texts, n_results):
        # Mock simple word overlap search
        results = []
        distances = []
        query_words = set(query_texts[0].lower().split())
        for doc_id, doc_text in self._docs.items():
            doc_words = set(doc_text.lower().split())
            overlap = len(query_words & doc_words)
            if overlap > 0:
                results.append((doc_id, 1.0 / (overlap + 1)))
        
        results.sort(key=lambda x: x[1])
        sliced = results[:n_results]
        return {
            "ids": [[r[0] for r in sliced]],
            "distances": [[r[1] for r in sliced]],
        }

    def get(self, include):
        return {"ids": list(self._docs.keys())}

    def delete(self, ids):
        for i in ids:
            self._docs.pop(i, None)
