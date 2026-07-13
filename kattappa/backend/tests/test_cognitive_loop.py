import unittest
from backend.core.cognitive_loop import CognitiveLoop

class TestCognitiveLoop(unittest.TestCase):
    """Unit tests verifying the main cognitive loop heartbeat."""

    def test_cognitive_cycle_execution(self) -> None:
        loop = CognitiveLoop()
        result = loop.execute_cycle("Book meeting tomorrow")
        
        # Verify intent, goals, plan, execute, observe, reflect, learn sequence
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("check_calendar", result["execution_steps"])
        self.assertIn("reserve_slot", result["execution_steps"])
        self.assertTrue(result["metrics"]["elapsed_time_seconds"] > 0)
        self.assertIsNotNone(result["reflections"])
        self.assertIn("what_happened", result["reflections"])
