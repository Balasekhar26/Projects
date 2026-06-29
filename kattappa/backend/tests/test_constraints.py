"""Unit and integration tests for Program 5G-4: Pluggable Constraint Engine.
"""
from __future__ import annotations

import time
import pytest

from backend.core.planning.task import Operator, Plan
from backend.core.planning.plan_graph import PlanNode, DependencyGraph, PlanCompiler
from backend.core.planning.constraints.models import ConstraintViolation, ConstraintReport
from backend.core.planning.constraints.engine import ConstraintEngine


def test_validator_enable_disable():
    """Verifies validators can be dynamically enabled or disabled at runtime."""
    engine = ConstraintEngine()
    engine.disable_validator("temporal_validator")
    
    validators = engine.get_validators()
    temp_val = next(v for v in validators if v["validator_id"] == "temporal_validator")
    assert temp_val["enabled"] is False

    engine.enable_validator("temporal_validator")
    validators = engine.get_validators()
    temp_val = next(v for v in validators if v["validator_id"] == "temporal_validator")
    assert temp_val["enabled"] is True


def test_temporal_validator_deadlines():
    """Verifies that TemporalValidator flags steps exceeding deadline constraints."""
    # Step 0 duration = 10, Step 1 duration = 5
    op1 = Operator("op1", "Task1", parameters={"deadline": 8.0}, estimated_time=10.0) # Fails deadline 8
    op2 = Operator("op2", "Task2", parameters={"deadline": 20.0}, estimated_time=5.0)

    plan = Plan("p1", "g1", steps=[op1, op2])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    engine = ConstraintEngine()
    report = engine.validate(graph, {"current_time": 0.0})
    
    assert report.passed is False
    assert len(report.violations) == 1
    assert "Task1" in report.violations[0].explanation
    assert report.violations[0].suggested_fix is not None


def test_resource_validator_conflicts():
    """Verifies that ResourceValidator flags exclusive resource conflicts in parallel layers."""
    # Two actions running in parallel that both require the 'camera' resource
    op_cam1 = Operator("cam1", "CaptureImage1", parameters={"required_resources": ["camera"]})
    op_cam2 = Operator("cam2", "CaptureImage2", parameters={"required_resources": ["camera"]})

    plan = Plan("p1", "g1", steps=[op_cam1, op_cam2])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    engine = ConstraintEngine()
    report = engine.validate(graph, {})

    assert report.passed is False
    # There should be a resource conflict violation since both are in Layer 0
    cam_violation = next(v for v in report.violations if v.constraint_id == "resource_validator")
    assert "Resource conflict on 'camera'" in cam_violation.explanation


def test_privacy_and_energy_validators():
    """Verifies privacy policy access block and battery drain limits."""
    # 1. Privacy Violation (unauthorized access)
    op_private = Operator("priv", "AccessPrivateDatabase", parameters={"access_private_data": True})
    plan_priv = Plan("p1", "g1", steps=[op_private])
    graph_priv = PlanCompiler.compile_plan_to_graph(plan_priv)

    engine = ConstraintEngine()
    report_priv = engine.validate(graph_priv, {"privacy_authorized": False})
    assert report_priv.passed is False
    assert any(v.constraint_id == "privacy_validator" for v in report_priv.violations)

    # 2. Energy Violation (exceeds battery level)
    op_drain = Operator("drain", "HighPowerExecution", parameters={"energy_cost": 40.0})
    plan_drain = Plan("p1", "g1", steps=[op_drain])
    graph_drain = PlanCompiler.compile_plan_to_graph(plan_drain)
    
    report_drain = engine.validate(graph_drain, {"battery_level": 30.0})
    assert report_drain.passed is False
    assert any(v.constraint_id == "energy_validator" for v in report_drain.violations)


def test_location_travel_warnings():
    """Verifies location validator flags warnings when travel transitions are required."""
    op_kitchen = Operator("kit", "CookFood", parameters={"required_location": "kitchen"})
    op_garage = Operator("gar", "FixCar", parameters={"required_location": "garage"})

    plan = Plan("p1", "g1", steps=[op_kitchen, op_garage])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    engine = ConstraintEngine()
    report = engine.validate(graph, {"current_location": "kitchen"})
    
    # Garage requires garage, so travel warning should trigger
    assert len(report.warnings) == 1
    assert report.warnings[0].constraint_id == "location_validator"
    assert "requires location 'garage'" in report.warnings[0].explanation


def test_repair_suggestions_generation():
    """Verifies that suggested fixes are gathered from violations."""
    op_private = Operator("priv", "AccessPrivateDatabase", parameters={"access_private_data": True})
    plan = Plan("p1", "g1", steps=[op_private])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    engine = ConstraintEngine()
    report = engine.validate(graph, {"privacy_authorized": False})
    
    repairs = engine.get_repair_suggestions(report)
    assert len(repairs) > 0
    assert "Request user permission" in repairs[0]
