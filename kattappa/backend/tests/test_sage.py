from __future__ import annotations

import unittest
from unittest.mock import patch
import sqlite3

from backend.core.memory import memory
from backend.core.sage import SAGE, SageKnowledgeGraph, SageUserModel, SageArchetypeKernel


class TestSageAlgorithm(unittest.TestCase):

    def setUp(self):
        # Clean up tables before each test
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            conn.execute("DELETE FROM sage_concepts")
            conn.execute("DELETE FROM sage_user_profile")
            conn.execute("DELETE FROM sage_archetypes")
            # Seed default archetypes
            defaults = [
                ("Rama", 0.2),
                ("Krishna", 0.2),
                ("Brahma", 0.2),
                ("Shiva", 0.2),
                ("Kattappa", 0.2),
            ]
            conn.executemany(
                "INSERT INTO sage_archetypes (name, weight, updated_at) VALUES (?, ?, datetime('now'))",
                defaults
            )

    def test_default_weights(self):
        weights = SageArchetypeKernel.get_weights()
        self.assertEqual(weights["Rama"], 0.2)
        self.assertEqual(weights["Krishna"], 0.2)
        self.assertEqual(weights["Brahma"], 0.2)
        self.assertEqual(weights["Shiva"], 0.2)
        self.assertEqual(weights["Kattappa"], 0.2)

    def test_add_and_update_concept(self):
        SageKnowledgeGraph.add_or_update_concept("FastAPI", confidence_delta=0.05)
        concepts = SageKnowledgeGraph.get_all_concepts()
        self.assertEqual(len(concepts), 1)
        self.assertEqual(concepts[0]["concept"], "FastAPI")
        self.assertAlmostEqual(concepts[0]["confidence"], 0.85)

        # Update it again
        SageKnowledgeGraph.add_or_update_concept("FastAPI", confidence_delta=0.05)
        concepts = SageKnowledgeGraph.get_all_concepts()
        self.assertAlmostEqual(concepts[0]["confidence"], 0.90)

    def test_user_model_profiling(self):
        # Short message should increase concise_preference
        SageUserModel.profile_user_input("short")
        profile = SageUserModel.get_profile()
        self.assertGreater(profile["concise_preference"], 0.5)

        # Technical words should increase technical_preference
        SageUserModel.profile_user_input("Check function python sqlite docker container code")
        profile = SageUserModel.get_profile()
        self.assertGreater(profile["technical_preference"], 0.5)

    @patch("backend.core.sage.ask_model")
    def test_sage_decide(self, mock_ask):
        mock_response = (
            "=== SCIENTIST ===\nScientist candidate response about git.\n"
            "=== ENGINEER ===\nEngineer candidate response about git.\n"
            "=== TEACHER ===\nTeacher candidate response about git.\n"
            "=== POET ===\nPoet candidate response about git."
        )
        mock_ask.side_effect = lambda prompt, role="fast", system=None: (
            "git, version_control" if "Extract a comma-separated" in prompt else mock_response
        )

        decision = SAGE.decide("how does git work?")
        self.assertIn("sage_", decision["selected_agent"])
        self.assertTrue(any(c["source"] == "engineer" for c in decision["candidates"]))
        self.assertGreater(len(decision["result"]), 0)

    def test_sage_learn_from(self):
        initial_weights = SageArchetypeKernel.get_weights()
        SAGE.learn_from("How does git work?", "sage_teacher", rating=1)
        new_weights = SageArchetypeKernel.get_weights()
        self.assertGreater(new_weights["Rama"], initial_weights["Rama"])
        self.assertGreater(new_weights["Kattappa"], initial_weights["Kattappa"])

    @patch("backend.core.sage.ask_model")
    def test_aether_self_questioning(self, mock_ask):
        from backend.core.sage import AetherSelfQuestioning
        mock_ask.return_value = "KNOW: Python code works\nASSUME: User has environment setup\nEVIDENCE: SQLite exists\nWRONG: Offline mode might trigger"
        res = AetherSelfQuestioning.evaluate("test", "context")
        self.assertEqual(res["know"], "Python code works")
        self.assertEqual(res["assume"], "User has environment setup")
        self.assertEqual(res["evidence"], "SQLite exists")
        self.assertEqual(res["wrong"], "Offline mode might trigger")

    @patch("backend.core.sage.ask_model")
    def test_aether_ethical_layer(self, mock_ask):
        from backend.core.sage import AetherEthicalLayer
        mock_ask.return_value = "truthfulness=0.95\nsafety=1.0\nfairness=0.90\nuser_benefit=0.95\nlong_term_impact=0.90"
        audit = AetherEthicalLayer.audit_response("query", "response")
        self.assertAlmostEqual(audit["truthfulness"], 0.95)
        self.assertAlmostEqual(audit["safety"], 1.0)
        self.assertAlmostEqual(audit["fairness"], 0.90)

    @patch("backend.core.sage.ask_model")
    def test_aether_creativity_engine(self, mock_ask):
        from backend.core.sage import AetherCreativityEngine
        mock_ask.return_value = "Analogous to a culinary chef mixing spices."
        analogy = AetherCreativityEngine.get_analogy("database")
        self.assertEqual(analogy, "Analogous to a culinary chef mixing spices.")

    def test_aether_confidence_tracking(self):
        from backend.core.sage import AetherConfidenceTracker
        self.assertEqual(AetherConfidenceTracker.compute_confidence(0, 0.0), "Unknown")
        self.assertEqual(AetherConfidenceTracker.compute_confidence(1, 0.9), "High")
        self.assertEqual(AetherConfidenceTracker.compute_confidence(1, 0.75), "Medium")
        self.assertEqual(AetherConfidenceTracker.compute_confidence(1, 0.5), "Low")

    def test_aether_memory_layers(self):
        from backend.core.sage import AetherMemoryLayer
        layers = AetherMemoryLayer.compile_all_layers("what is docker?", "active plan")
        self.assertIn("sensory", layers)
        self.assertIn("working", layers)
        self.assertIn("semantic", layers)
        self.assertIn("procedural", layers)
        self.assertIn("user", layers)
        self.assertIn("long_term", layers)
        self.assertEqual(layers["sensory"]["character_count"], 15)
