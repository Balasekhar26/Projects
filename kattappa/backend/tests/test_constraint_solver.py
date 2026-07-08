"""Unit tests for Program 12.2 Constraint Solver and Reservation Manager.
"""
from __future__ import annotations

import time
import pytest
from backend.core.planning.task_library import TaskLibrary
from backend.core.planning.htn_planner import HTNPlanner
from backend.core.planning.constraint_types import Severity, ConstraintNamespace
from backend.core.planning.constraint_solver import ConstraintSolver
from backend.core.planning.reservation_manager import ReservationManager


def test_constraint_solver_hard_and_soft_violations():
    """Verifies that hard constraints block plans and soft constraints penalize utility."""
    planner = HTNPlanner()
    solver = ConstraintSolver()

    # Generate a standard plan
    plan = planner.generate_plan(
        goal_id="demo-goal",
        root_task_name="PrepareDemoSystem",
        initial_state=["internet_available"]
    )

    # 1. Test satisfied constraints (clean world state)
    world_state_ok = {
        "max_plan_duration": 100.0,
        "financial_budget": 50.0,
        "offline_mode": False,
    }
    result_ok = solver.validate_plan(plan, world_state_ok)
    assert result_ok.is_feasible is True
    assert len(result_ok.violations) == 0
    assert result_ok.utility_penalty == 0.0

    # 2. Test HARD constraint violation (insufficient budget)
    world_state_tight_budget = {
        "max_plan_duration": 100.0,
        "financial_budget": 0.5,  # Plan needs $1.5
        "offline_mode": False,
    }
    result_hard = solver.validate_plan(plan, world_state_tight_budget)
    assert result_hard.is_feasible is False
    assert len(result_hard.violations) == 1
    
    violation = result_hard.violations[0]
    assert violation.severity == Severity.HARD
    assert "exceeds budget limit" in violation.reason
    assert "remediation" in violation.to_dict()

    # 3. Test SOFT constraint violation (offline policy breach)
    world_state_offline = {
        "max_plan_duration": 100.0,
        "financial_budget": 50.0,
        "offline_mode": True,  # Will trigger offline API warning for DownloadBinary
    }
    result_soft = solver.validate_plan(plan, world_state_offline)
    assert result_soft.is_feasible is True  # Soft constraints do not block feasibility
    assert len(result_soft.violations) == 1
    assert result_soft.violations[0].severity == Severity.SOFT
    assert result_soft.utility_penalty == 0.25


def test_reservation_manager_lock_and_collision():
    """Verifies that ReservationManager manages allocations, collisions, and release."""
    # Capacity pool: 4.0 CPU, 2.0 GPU
    manager = ReservationManager(capacity={"cpu": 4.0, "gpu": 2.0})

    # Reserve 2.0 CPU and 1.0 GPU
    res_id_1 = manager.reserve(plan_id="plan-1", resource_vector={"cpu": 2.0, "gpu": 1.0})
    assert res_id_1.startswith("res-")
    assert manager.available_resources["cpu"] == 2.0
    assert manager.available_resources["gpu"] == 1.0

    # Try reserving another 3.0 CPU -> Should raise collision/exhaustion error
    with pytest.raises(ValueError) as excinfo:
        manager.reserve(plan_id="plan-2", resource_vector={"cpu": 3.0})
    assert "Insufficient 'cpu'" in str(excinfo.value)

    # Allocate the reservation
    manager.allocate(res_id_1)
    
    # Releasing should restore CPU capacity back to 4.0
    manager.release(res_id_1)
    assert manager.available_resources["cpu"] == 4.0
    assert manager.available_resources["gpu"] == 2.0


def test_reservation_manager_sweep_and_expiry():
    """Verifies that expired reservation leases are swept and capacities returned to pool."""
    manager = ReservationManager(capacity={"cpu": 4.0})

    # Reserve with 0.1s lease duration
    res_id = manager.reserve(plan_id="plan-1", resource_vector={"cpu": 2.0}, lease_duration=0.1)
    assert manager.available_resources["cpu"] == 2.0

    # Wait for expiry
    time.sleep(0.15)

    # Sweep reservations
    expired_count = manager.expire_stale_reservations()
    assert expired_count == 1
    assert manager.reservations[res_id].status == "EXPIRED"
    assert manager.available_resources["cpu"] == 4.0
