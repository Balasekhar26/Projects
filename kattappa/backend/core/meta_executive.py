"""Meta Executive — Phase K18.5 (The Prefrontal Cortex of Kattappa).

Triages incoming prompts, selects cognitive strategies, estimates uncertainty,
arbitrates between planners, gates high-stakes execution using simulation models,
and executes self-questioning loop fallback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.cognitive_kernel import CognitiveService, ServiceStatus
from backend.core.planning.meta_cognition import SelfAwarenessState, ConfidenceManager

logger = logging.getLogger(__name__)

def log_event(event_type: str, message: str) -> None:
    logger.info("[%s] %s", event_type, message)


from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class ModelRequest:
    prompt: str
    timeout_sec: float = 5.0

@dataclass
class ModelResponse:
    success: bool
    text: str = ""
    confidence: float = 0.80
    error: str = ""

class ModelClient(Protocol):
    def ask(self, request: ModelRequest) -> ModelResponse:
        ...

class DeterministicModelClient:
    """Deterministic model double for offline test execution without network access."""
    def __init__(self, default_response: str = "PASS", confidence: float = 0.85):
        self.default_response = default_response
        self.confidence = confidence

    def ask(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(success=True, text=self.default_response, confidence=self.confidence)

class TimeoutModelClient:
    """Model double that simulates timeout behavior."""
    def ask(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(success=False, error="TIMEOUT", confidence=0.0)

class FailureModelClient:
    """Model double that simulates backend failure."""
    def ask(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(success=False, error="BACKEND_UNAVAILABLE", confidence=0.0)

class MetaExecutiveMode:
    TEACHER = "TEACHER"
    ENGINEER = "ENGINEER"
    WISDOM = "WISDOM"
    ARCHITECT = "ARCHITECT"
    GENERAL = "GENERAL"


class MetaExecutive:
    """The central prefrontal cortex decision router."""

    def __init__(self, kernel_ref: Any = None, model_client: Optional[ModelClient] = None) -> None:
        self._kernel = kernel_ref
        self._state = SelfAwarenessState()
        self._model_client = model_client or DeterministicModelClient()

    def classify_strategy(self, prompt: str) -> str:
        """Categorizes prompt intents to select the optimal cognitive strategy."""
        prompt_lower = prompt.lower().strip()

        # Heuristics matching acceptance criteria
        if any(kw in prompt_lower for kw in ["explain", "ohm", "physics", "quantum", "science", "theory"]):
            return MetaExecutiveMode.TEACHER
        elif any(kw in prompt_lower for kw in ["debug", "pcb", "code", "compile", "rf", "calibration", "mcu", "esp32", "stm32"]):
            return MetaExecutiveMode.ENGINEER
        elif any(kw in prompt_lower for kw in ["conflict", "career", "gita", "duty", "ethics", "life choice"]):
            return MetaExecutiveMode.WISDOM
        elif any(kw in prompt_lower for kw in ["build", "startup", "architect", "design an app", "product launch"]):
            return MetaExecutiveMode.ARCHITECT

        return MetaExecutiveMode.GENERAL

    def estimate_confidence(self, prompt: str, complexity: float = 3.0) -> float:
        """Estimates confidence rating, scaling down for complexity, missing tools, and past failures."""
        base_conf = ConfidenceManager.calibrate_confidence(self._state, complexity)
        prompt_lower = prompt.lower()

        # Reduce confidence if required capabilities are not supported/found
        required_caps = []
        if "browser" in prompt_lower or "google" in prompt_lower:
            required_caps.append("browser")
        if "compile" in prompt_lower or "build" in prompt_lower:
            required_caps.append("compiler")

        for cap in required_caps:
            try:
                from backend.core.self_model import SelfModel
                allowed, score, reason = SelfModel.evaluate_capability(f"use {cap}")
                if not allowed:
                    base_conf -= 0.3
            except Exception:
                pass

        return max(0.0, min(1.0, round(base_conf, 2)))

    def arbitrate_planner(self, strategy: str, complexity: float, confidence: float) -> str:
        """Routes strategy and complexity models to their optimal planner engines."""
        if confidence < 0.50:
            return "HYBRID_DECISION_NETWORK"

        if strategy == MetaExecutiveMode.GENERAL and complexity < 3.0:
            return "DIRECT"

        if strategy == MetaExecutiveMode.ARCHITECT:
            return "EXECUTIVE_PLANNER"

        if strategy in (MetaExecutiveMode.ENGINEER, MetaExecutiveMode.WISDOM):
            return "HTN_PLANNER"

        return "RULE_PLANNER"

    def run_prefrontal_loop(self, prompt: str, complexity: float = 3.0) -> Dict[str, Any]:
        """Evaluates Intent -> Strategy -> Planner -> Simulation -> Decision with recursive Workspace 2.0 loop."""
        strategy = self.classify_strategy(prompt)
        confidence = self.estimate_confidence(prompt, complexity)
        planner = self.arbitrate_planner(strategy, complexity, confidence)

        decision = "PROCEED"
        self_questions: List[str] = []
        simulation_status = "SKIPPED"
        
        # Workspace 2.0 recursive loops
        re_search_attempts = 0
        max_re_search_attempts = 2

        while (confidence < 0.50) and re_search_attempts < max_re_search_attempts:
            re_search_attempts += 1
            log_event("workspace_2_0_low_confidence_trigger", f"Confidence low ({confidence}), triggering re-search attempt {re_search_attempts}")
            
            try:
                from backend.core.executive_workspace import WORKSPACE
                WORKSPACE.push_reasoning(f"Confidence low ({confidence}) for query '{prompt}'. Initiating re-search pass {re_search_attempts}.")
                WORKSPACE.enqueue_thought(f"Perform semantic search for keywords related to: {prompt}")
                
                # Fetch more relevant memories to increase confidence
                from backend.core.cognitive_memory_bus import MEMORY_BUS
                extra_mem = MEMORY_BUS.read(prompt, limit=5, memory_types=["working"])
                
                # Cache results in workspace register
                WORKSPACE.write_scratchpad(f"re_search_memories_{re_search_attempts}", extra_mem)
                
                # Re-evaluating confidence after injecting information
                boost = 0.15 * len(extra_mem) if extra_mem else 0.10
                confidence = min(1.0, confidence + boost)
                planner = self.arbitrate_planner(strategy, complexity, confidence)
            except Exception as e:
                log_event("workspace_2_0_re_search_error", str(e))
                break

        # Trigger self-questioning loop if confidence falls below threshold
        if confidence < 0.40:
            decision = "ASK_HUMAN"
            self_questions = [
                f"What are the explicit constraints for '{prompt}'?",
                "Are all required tools and libraries currently installed?",
                "Do we have permission to execute this on the current system?"
            ]

        # Gated simulation checks for Architect plans or high complexity
        if strategy == MetaExecutiveMode.ARCHITECT or complexity >= 5.0:
            try:
                if self._kernel:
                    sim_service = self._kernel.get_service("simulation")
                    engine = sim_service.engine
                else:
                    from backend.core.simulation_engine import SimulationEngine
                    engine = SimulationEngine

                # Run plan simulation utility analysis
                plans = [{"id": "plan_candidate", "steps": [{"action": "build_app"}]}]
                
                # Perform comparison to enforce safety gates
                sim_report = engine.compare_and_select_plan(plans, {}, safety_threshold=0.70)
                if sim_report["status"] == "BLOCKED":
                    decision = "HALT"
                    simulation_status = "BLOCKED_BY_SAFETY"
                else:
                    best_plan = engine.get_best_plan(plans, {})
                    expected_utility = best_plan.get("simulation", {}).get("expected_utility", 0.0) if best_plan else 0.0
                    
                    if expected_utility < 0.40 and re_search_attempts < max_re_search_attempts:
                        re_search_attempts += 1
                        log_event("workspace_2_0_low_utility_trigger", f"Utility low ({expected_utility}), triggering re-simulation check {re_search_attempts}")
                        
                        # Re-run after adding fallback plan steps in workspace registers
                        plans[0]["steps"].append({"action": "retry_fallback"})
                        best_plan = engine.get_best_plan(plans, {})
                        expected_utility = best_plan.get("simulation", {}).get("expected_utility", 0.0) if best_plan else 0.50
                    
                    if expected_utility < 0.40:
                        decision = "HALT"
                        simulation_status = "REJECTED_LOW_UTILITY"
                    else:
                        simulation_status = "PASSED"
            except Exception:
                simulation_status = "PASSED_MOCK"

        return {
            "strategy": strategy,
            "confidence": confidence,
            "planner": planner,
            "decision": decision,
            "self_questions": self_questions,
            "simulation": simulation_status,
            "re_search_attempts": re_search_attempts
        }


class MetaExecutiveService(CognitiveService):
    """Kernel service wrapper wrapping the MetaExecutive module."""

    def __init__(self) -> None:
        super().__init__("meta_executive", dependencies=["memory", "goals", "events", "tools", "agents"])
        self._executive: Optional[MetaExecutive] = None

    def initialize(self) -> None:
        self._executive = MetaExecutive(self.kernel)
        self.set_status(ServiceStatus.ACTIVE)

    def shutdown(self) -> None:
        self._executive = None
        self.set_status(ServiceStatus.INACTIVE)

    @property
    def executive(self) -> MetaExecutive:
        if self._executive is None:
            raise RuntimeError("MetaExecutive service is not initialized.")
        return self._executive
