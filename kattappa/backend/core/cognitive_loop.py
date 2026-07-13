from __future__ import annotations
import uuid
import time
from typing import Any, Dict
from backend.core.orchestrator import Orchestrator

class CognitiveLoop:
    """The central execution loop that coordinates Kattappa's persistent intelligence heartbeat."""

    def __init__(self) -> None:
        self.orchestrator = Orchestrator()

    def execute_cycle(self, user_input: str) -> Dict[str, Any]:
        """Runs the complete cognitive processing cycle from intake to response generation."""
        start_time = time.time()
        
        # Invoke cognitive loop orchestration
        result = self.orchestrator.run(user_input)
        
        elapsed_time = time.time() - start_time
        result["metrics"] = {
            "elapsed_time_seconds": elapsed_time,
            "timestamp": time.time()
        }
        
        return result
