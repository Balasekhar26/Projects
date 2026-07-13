from __future__ import annotations
import unittest
import os
import time
from backend.knowledge_graph.triple import Triple
from backend.knowledge_graph.graph_store import GraphStore
from backend.reasoning.inference_engine import InferenceEngine
from backend.reasoning.utility_adjuster import UtilityAdjuster

class TestReasoningEngine(unittest.TestCase):
    """Integration test suite validating Phase 4E Semantic Reasoning Engine."""

    def setUp(self) -> None:
        self.db_path = "backend/data/test_reasoning.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.store = GraphStore(self.db_path)
        self.inference_engine = InferenceEngine(self.store)
        self.utility_adjuster = UtilityAdjuster(self.store)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_multi_hop_inference_and_explanation(self) -> None:
        # User works at Zen (confidence = 0.90)
        t1 = Triple("user", "WORKS_AT", "Zen", 0.90, time.time(), "source1")
        # Zen located in Hyderabad (confidence = 0.95)
        t2 = Triple("Zen", "LOCATED_IN", "Hyderabad", 0.95, time.time(), "source2")
        
        self.store.add_triple(t1)
        self.store.add_triple(t2)

        # Run inferences
        inferred = self.inference_engine.run_inference()
        
        # Verify a new relationship was deduced
        self.assertEqual(len(inferred), 1)
        derived_triple, explanation = inferred[0]
        
        self.assertEqual(derived_triple.subject, "user")
        self.assertEqual(derived_triple.predicate, "LOCATED_IN")
        self.assertEqual(derived_triple.object, "Hyderabad")
        # Inferred confidence: 0.90 * 0.95 * 0.95 (transitive step decay) = ~0.81
        self.assertAlmostEqual(derived_triple.confidence, 0.81, places=2)
        
        # Verify explanation text contains key parts
        self.assertIn("Transitive Location Rule", explanation)
        self.assertIn("user works at zen", explanation.lower())

        # Verify fact was persisted to database as active fact
        stored_triples = self.store.get_triples(subject="user", predicate="LOCATED_IN")
        self.assertEqual(len(stored_triples), 1)
        self.assertEqual(stored_triples[0].object, "Hyderabad")

    def test_utility_adjuster_preferences(self) -> None:
        # Add preference fact to storage: user prefers afternoon meetings
        pref = Triple("user", "PREFERS", "afternoon meetings", 0.90, time.time(), "source")
        self.store.add_triple(pref)

        # Morning slot meeting payload
        morning_payload = {"time": "10:00 AM", "title": "Morning Sync"}
        morning_utility = self.utility_adjuster.adjust_utility("create_meeting", morning_payload, 0.80)
        # Utility should be penalized by 0.35: 0.80 - 0.35 = 0.45
        self.assertAlmostEqual(morning_utility, 0.45, places=2)

        # Afternoon slot meeting payload
        afternoon_payload = {"time": "3:00 PM", "title": "Afternoon Sync"}
        afternoon_utility = self.utility_adjuster.adjust_utility("create_meeting", afternoon_payload, 0.80)
        # Utility should remain intact: 0.80
        self.assertAlmostEqual(afternoon_utility, 0.80, places=2)

if __name__ == "__main__":
    unittest.main()
