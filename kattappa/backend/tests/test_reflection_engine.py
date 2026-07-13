import os
import unittest
from pathlib import Path
from backend.core.reflection_engine import ReflectionEngine

class TestReflectionEngine(unittest.TestCase):
    """Unit tests verifying execution reflections and storage properties."""

    def test_reflect_on_execution(self) -> None:
        state = {
            "user_input": "Verify version and compile",
            "execution_plan": ["compile_code", "run_tests"],
            "result": "SUCCESS",
            "logs": ["test log 1"]
        }
        
        reflection = ReflectionEngine.reflect_on_execution(state)
        
        self.assertEqual(reflection["why_failure_occurred"], "None")
        self.assertTrue(reflection["should_memory_be_updated"])
        
        # Verify stored reflection file
        reflections_dir = Path("evaluation/reflections")
        self.assertTrue(reflections_dir.exists())
        self.assertTrue(len(os.listdir(reflections_dir)) > 0)
