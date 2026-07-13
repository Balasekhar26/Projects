from __future__ import annotations
import unittest
import time
import os
import sqlite3
from backend.knowledge_graph.triple import Triple
from backend.knowledge_graph.graph_store import GraphStore
from backend.knowledge_graph.extractor import TripleExtractor
from backend.knowledge_graph.graph_query import GraphQueryEngine
from backend.knowledge_graph.temporal_decay import TemporalDecayEngine

class TestKnowledgeGraphIntegration(unittest.TestCase):
    """Integration test suite validating Phase 4C Knowledge Graph components."""

    def setUp(self) -> None:
        self.db_path = "backend/data/test_knowledge_graph.db"
        # Ensure clean state
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.store = GraphStore(self.db_path)
        self.query_engine = GraphQueryEngine(self.store)
        self.decay_engine = TemporalDecayEngine(self.store)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_triple_extraction_and_persistence(self) -> None:
        query = "Book meeting tomorrow at 3PM with engineering - prefers afternoon meetings in Hyderabad"
        entities = {
            "intent": "schedule_meeting",
            "participants": ["engineering"],
            "datetime": "2026-07-12T15:00:00"
        }
        
        triples = TripleExtractor.extract_from_query(query, entities)
        self.assertTrue(len(triples) >= 3)
        
        # Verify specific values in extracted triples
        subjects = [t.subject for t in triples]
        self.assertIn("user", subjects)
        self.assertIn("meeting", subjects)

        for t in triples:
            self.store.add_triple(t)

        active_triples = self.store.get_triples(status="ACTIVE")
        self.assertEqual(len(active_triples), len(triples))

    def test_contradiction_resolution(self) -> None:
        # User lives in Hyderabad (confidence=0.90)
        t1 = Triple("user", "LOCATED_IN", "Hyderabad", 0.90, time.time(), "source1")
        self.store.add_triple(t1)
        
        # Query active location
        self.assertEqual(self.query_engine.get_user_location(), "Hyderabad")
        
        # User lives in Guntur (higher confidence=0.95)
        t2 = Triple("user", "LOCATED_IN", "Guntur", 0.95, time.time(), "source2")
        self.store.add_triple(t2)
        
        # Guntur should override Hyderabad
        self.assertEqual(self.query_engine.get_user_location(), "Guntur")
        
        # Hyderabad should be demoted to historical
        hist_triples = self.store.get_triples(subject="user", predicate="LOCATED_IN", status="HISTORICAL")
        self.assertEqual(len(hist_triples), 1)
        self.assertEqual(hist_triples[0].object, "Hyderabad")

    def test_temporal_decay(self) -> None:
        # Insert a fact with timestamp set to 10 days ago
        ten_days_ago = time.time() - (10 * 24 * 3600)
        t = Triple("user", "PREFERS", "afternoon meetings", 0.90, ten_days_ago, "source")
        
        # We manually insert it into sqlite to set the older timestamp
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO triples (subject, predicate, object, confidence, timestamp, source, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (t.subject, t.predicate, t.object, t.confidence, t.timestamp, t.source, "ACTIVE")
        )
        conn.commit()
        conn.close()

        # Apply decay of 0.05 per day (10 days * 0.05 = 0.50 decay score)
        self.decay_engine.apply_decay(decay_rate_per_day=0.05)
        
        # Fetch decayed triple
        decayed = self.store.get_triples(subject="user", predicate="PREFERS")[0]
        # Expected new confidence: 0.90 - 0.50 = 0.40
        self.assertAlmostEqual(decayed.confidence, 0.40, places=2)

if __name__ == "__main__":
    unittest.main()
