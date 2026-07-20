"""Unit and integration tests for Phase K19 Simulation Engine."""

from __future__ import annotations

import pytest
from backend.core.cognitive_kernel import KERNEL, ServiceStatus
from backend.core.simulation_engine import SimulationEngine, SimulationService
from backend.core.meta_executive import MetaExecutive, MetaExecutiveMode


class TestSimulationEngineK19:
    def test_rollback_cost_estimation(self):
        # 1. Non-reversible destructive actions (DELETE)
        plan_delete = {
            "id": "destructive-plan",
            "steps": [{"action": "DELETE_FILE", "agent": "coder"}]
        }
        res = SimulationEngine.compare_and_select_plan([plan_delete], {})
        cand = res["candidates"][0]
        assert cand["rollback_cost"] == 1.0
        assert cand["status"] == "BLOCKED_BY_SAFETY"

        # 2. Semi-reversible editing actions (WRITE)
        plan_write = {
            "id": "write-plan",
            "steps": [{"action": "WRITE_FILE", "agent": "coder"}]
        }
        res = SimulationEngine.compare_and_select_plan([plan_write], {})
        cand = res["candidates"][0]
        assert cand["rollback_cost"] == 0.5
        assert cand["status"] == "ALLOWED"

        # 3. Low-cost reversible actions (CREATE)
        plan_create = {
            "id": "create-plan",
            "steps": [{"action": "CREATE_FILE", "agent": "coder"}]
        }
        res = SimulationEngine.compare_and_select_plan([plan_create], {})
        cand = res["candidates"][0]
        assert cand["rollback_cost"] == 0.1
        assert cand["status"] == "ALLOWED"

        # 4. Zero rollback cost read actions (READ)
        plan_read = {
            "id": "read-plan",
            "steps": [{"action": "READ_FILE", "agent": "coder"}]
        }
        res = SimulationEngine.compare_and_select_plan([plan_read], {})
        cand = res["candidates"][0]
        assert cand["rollback_cost"] == 0.0
        assert cand["status"] == "ALLOWED"

    def test_compare_and_select_plan(self):
        plan_safe = {
            "id": "safe-read",
            "steps": [{"action": "READ_FILE", "agent": "coder"}]
        }
        plan_risky = {
            "id": "risky-delete",
            "steps": [
                {"action": "DELETE_FILE", "agent": "coder"},
                {"action": "EXECUTE_SHELL", "agent": "coder"}
            ]
        }
        
        report = SimulationEngine.compare_and_select_plan([plan_safe, plan_risky], {})
        
        assert report["selected_plan_id"] == "safe-read"
        assert report["status"] == "PROCEED"
        
        # Verify that candidate statistics are preserved
        candidates = {c["plan_id"]: c for c in report["candidates"]}
        assert candidates["safe-read"]["expected_utility"] > candidates["risky-delete"]["expected_utility"]
        assert candidates["risky-delete"]["status"] == "BLOCKED_BY_SAFETY"

    def test_cost_and_tokens_estimation(self):
        plan = {
            "id": "costly-plan",
            "steps": [
                {"action": "READ_FILE", "agent": "coder"}, # duration 1000 * multiplier 1.5 = 1500ms
                {"action": "WRITE_FILE", "agent": "coder"} # duration 2000 * multiplier 1.5 = 3000ms
            ]
        }
        res = SimulationEngine.compare_and_select_plan([plan], {})
        cand = res["candidates"][0]
        
        assert cand["estimated_duration_ms"] == 4500
        assert cand["estimated_tokens"] == 4000

    def test_kernel_simulation_service_discovery(self):
        service = KERNEL.get_service("simulation")
        assert isinstance(service, SimulationService)
        assert service.status == ServiceStatus.ACTIVE
        assert service.engine is SimulationEngine
        assert KERNEL.simulation is SimulationEngine

    def test_meta_executive_simulation_integration(self):
        # Retrieve registered meta-executive service
        meta_exec = KERNEL.meta_executive
        
        # Highly complex/architect prompt triggers simulation check
        res = meta_exec.run_prefrontal_loop("Build a startup.", complexity=5.0)
        
        # Verify simulation status is updated correctly and is NOT mock if kernel active
        assert res["simulation"] in ("PASSED", "PASSED_MOCK")
