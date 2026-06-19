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
        # Thumbs up for teacher should reinforce Rama and Kattappa
        SAGE.learn_from("How does git work?", "sage_teacher", rating=1)
        new_weights = SageArchetypeKernel.get_weights()

        self.assertGreater(new_weights["Rama"], initial_weights["Rama"])
        self.assertGreater(new_weights["Kattappa"], initial_weights["Kattappa"])
        self.assertLess(new_weights["Krishna"], initial_weights["Krishna"])  # Krishna should decrease relatively after normalization
