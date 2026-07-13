import unittest
from backend.core.orchestrator import Orchestrator

class TestOrchestrator(unittest.TestCase):
    """Unit tests verifying the cognitive orchestrator's state transitions."""

    def test_orchestration_state_transitions(self) -> None:
        orchestrator = Orchestrator()
        result = orchestrator.run("Install software")
        
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("download_package", result["execution_steps"])
        self.assertIn("run_installer", result["execution_steps"])
        self.assertTrue(len(result["logs"]) > 5)
