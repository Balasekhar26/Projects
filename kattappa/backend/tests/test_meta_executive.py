"""Unit tests for Phase K18.5 Meta Executive."""

from __future__ import annotations

import pytest
from backend.core.cognitive_kernel import KERNEL, ServiceStatus
from backend.core.meta_executive import MetaExecutive, MetaExecutiveMode, MetaExecutiveService
from backend.core.model_clients import UnavailableModelClient, ConfiguredModelClient, ModelRequest
from backend.core.planning.meta_cognition import SelfAwarenessState
from backend.tests.support import DeterministicModelClient, TimeoutModelClient, FailureModelClient


class TestMetaExecutive:
    def test_strategy_classification(self):
        exec_ctx = MetaExecutive()
        
        # Teacher Mode
        assert exec_ctx.classify_strategy("Explain Ohm's law.") == MetaExecutiveMode.TEACHER
        assert exec_ctx.classify_strategy("Explain quantum physics to a 10 year old in Telugu.") == MetaExecutiveMode.TEACHER
        
        # Engineer Mode
        assert exec_ctx.classify_strategy("Debug this PCB.") == MetaExecutiveMode.ENGINEER
        assert exec_ctx.classify_strategy("Compile the ESP32 code and run diagnostics.") == MetaExecutiveMode.ENGINEER
        
        # Wisdom Mode
        assert exec_ctx.classify_strategy("I am conflicted about my career.") == MetaExecutiveMode.WISDOM
        assert exec_ctx.classify_strategy("Tell me Gita guidance on duty and conflict.") == MetaExecutiveMode.WISDOM
        
        # Architect Mode
        assert exec_ctx.classify_strategy("Build a startup from scratch.") == MetaExecutiveMode.ARCHITECT
        assert exec_ctx.classify_strategy("Build an app.") == MetaExecutiveMode.ARCHITECT
        
        # General Mode
        assert exec_ctx.classify_strategy("What is your current health status?") == MetaExecutiveMode.GENERAL

    def test_planner_routing(self):
        exec_ctx = MetaExecutive()
        
        # Low complexity, general mode -> DIRECT
        assert exec_ctx.arbitrate_planner(MetaExecutiveMode.GENERAL, complexity=1.0, confidence=0.90) == "DIRECT"
        
        # Low confidence -> HYBRID_DECISION_NETWORK
        assert exec_ctx.arbitrate_planner(MetaExecutiveMode.GENERAL, complexity=2.0, confidence=0.30) == "HYBRID_DECISION_NETWORK"
        
        # Architect -> EXECUTIVE_PLANNER
        assert exec_ctx.arbitrate_planner(MetaExecutiveMode.ARCHITECT, complexity=4.0, confidence=0.85) == "EXECUTIVE_PLANNER"
        
        # Engineer/Wisdom -> HTN_PLANNER
        assert exec_ctx.arbitrate_planner(MetaExecutiveMode.ENGINEER, complexity=3.0, confidence=0.75) == "HTN_PLANNER"
        assert exec_ctx.arbitrate_planner(MetaExecutiveMode.WISDOM, complexity=3.0, confidence=0.75) == "HTN_PLANNER"

    def test_prefrontal_loop_low_confidence_invokes_model_client(self):
        client = DeterministicModelClient(default_response="Specific refined question?", confidence=0.30)
        exec_ctx = MetaExecutive(model_client=client)
        exec_ctx._state = SelfAwarenessState(uncertainty=0.8, failure_count=2)
        
        res = exec_ctx.run_prefrontal_loop("Build a startup.", complexity=5.0)
        assert res["decision"] == "ASK_HUMAN"
        assert res["self_questions"] == ["Specific refined question?"]
        assert client.call_count == 1

    def test_prefrontal_loop_high_confidence(self):
        client = DeterministicModelClient(confidence=0.90)
        exec_ctx = MetaExecutive(model_client=client)
        exec_ctx._state = SelfAwarenessState(uncertainty=0.1, failure_count=0)
        
        res = exec_ctx.run_prefrontal_loop("Explain Ohm's law.", complexity=2.0)
        assert res["strategy"] == MetaExecutiveMode.TEACHER
        assert res["decision"] == "PROCEED"
        assert len(res["self_questions"]) == 0
        assert client.call_count == 0

    def test_prefrontal_loop_unavailable_default_client(self):
        exec_ctx = MetaExecutive()  # defaults to UnavailableModelClient
        exec_ctx._state = SelfAwarenessState(uncertainty=0.8, failure_count=2)
        
        res = exec_ctx.run_prefrontal_loop("Build a startup.", complexity=5.0)
        assert res["decision"] == "ASK_HUMAN"
        assert len(res["self_questions"]) > 0

    def test_configured_client_connection_refused(self):
        client = ConfiguredModelClient(endpoint_url="http://127.0.0.1:59999/api/generate", request_timeout_sec=0.5)
        resp = client.ask(ModelRequest(prompt="Test"))
        assert resp.success is False
        assert resp.error in ("CONNECTION_REFUSED", "URLError")

    def test_prefrontal_loop_timeout_client(self):
        client = TimeoutModelClient()
        resp = client.ask(ModelRequest(prompt="Test"))
        assert resp.success is False
        assert resp.error == "TIMEOUT"

    def test_prefrontal_loop_failure_client(self):
        client = FailureModelClient()
        resp = client.ask(ModelRequest(prompt="Test"))
        assert resp.success is False
        assert resp.error == "BACKEND_UNAVAILABLE"

    def test_kernel_service_discovery(self):
        service = KERNEL.get_service("meta_executive")
        assert isinstance(service, MetaExecutiveService)
        assert service.status == ServiceStatus.ACTIVE
        assert isinstance(service.executive, MetaExecutive)
        assert KERNEL.meta_executive is service.executive
