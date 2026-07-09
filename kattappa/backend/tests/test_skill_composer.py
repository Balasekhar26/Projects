"""Unit tests for Program 56.0: Skill Composer.

Verifies skill composition, cycle detection, parallel branch groupings, fallback paths,
and critical-path cost calculations.
"""
from __future__ import annotations

import pytest

from backend.core.skill_composer import SkillComposer


def test_compose_skills_success():
    skills = [
        {"name": "Run Tests", "cost_profile": "low"},
        {"name": "Build Container", "cost_profile": "medium"},
        {"name": "Deploy Service", "cost_profile": "high"},
        {"name": "Security Scan", "cost_profile": "medium"},
    ]

    dependencies = {
        "Build Container": ["Run Tests"],
        "Deploy Service": ["Build Container", "Security Scan"],
    }

    fallbacks = {
        "Deploy Service": "Build Container",
    }

    composed = SkillComposer.compose_skills(
        name="Deploy FastAPI Application",
        description="Validates, builds, and deploys a FastAPI container.",
        skills=skills,
        dependencies=dependencies,
        fallbacks=fallbacks,
    )

    assert composed.name == "Deploy FastAPI Application"
    assert composed.fallback_plan["Deploy Service"] == "Build Container"

    # Verify execution layers (topological sorting satisfying dependencies)
    # Layer 0: Run Tests, Security Scan (in-degrees = 0)
    # Layer 1: Build Container (depends on Run Tests)
    # Layer 2: Deploy Service (depends on Build Container, Security Scan)
    assert composed.execution_plan == [
        ["Run Tests", "Security Scan"],
        ["Build Container"],
        ["Deploy Service"],
    ]

    # Verify cost estimations
    # Total cost = 1.0 (Run Tests) + 5.0 (Build Container) + 15.0 (Deploy Service) + 5.0 (Security Scan) = 26.0
    # Latency:
    # Layer 0: max(10.0 [Run Tests], 30.0 [Security Scan]) = 30.0
    # Layer 1: max(30.0 [Build Container]) = 30.0
    # Layer 2: max(90.0 [Deploy Service]) = 90.0
    # Total critical path latency = 30.0 + 30.0 + 90.0 = 150.0
    assert composed.estimated_cost["total_cost"] == 26.0
    assert composed.estimated_cost["critical_path_latency"] == 150.0


def test_compose_skills_cyclic_dependency_raises_value_error():
    skills = [
        {"name": "Skill A"},
        {"name": "Skill B"},
    ]

    dependencies = {
        "Skill A": ["Skill B"],
        "Skill B": ["Skill A"],
    }

    with pytest.raises(ValueError, match="Cyclic dependency detected"):
        SkillComposer.compose_skills(
            name="Cyclic Task",
            description="Should fail",
            skills=skills,
            dependencies=dependencies,
        )


def test_compose_skills_missing_reference_raises_value_error():
    skills = [
        {"name": "Skill A"},
    ]

    dependencies = {
        "Skill A": ["Skill Missing"],
    }

    with pytest.raises(ValueError, match="referenced by 'Skill A' is missing"):
        SkillComposer.compose_skills(
            name="Missing Ref Task",
            description="Should fail",
            skills=skills,
            dependencies=dependencies,
        )
