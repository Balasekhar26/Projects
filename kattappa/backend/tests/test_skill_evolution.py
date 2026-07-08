"""Unit tests for Program 23.0: Self-Improving Skill Evolution.

Validates lifecycle evaluations, trust demotions, and step template upgrades in SkillLibrary.
"""
from __future__ import annotations

import pytest
from backend.core.skill_library import SkillLibrary
from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory
from backend.core.learning.skill_optimizer import SkillOptimizer


@pytest.fixture(autouse=True)
def clean_skill_library():
    SkillLibrary.reset()
    yield
    SkillLibrary.reset()


class TestSkillEvolution:
    def test_evaluate_insufficient_runs(self):
        SkillLibrary.add_skill(
            name="CompileService",
            description="Build steps",
            inputs=[],
            steps=["CompileNode"],
            outputs=[],
            tags=["build"]
        )

        store = ExperienceStore()
        # 3 runs (less than threshold of 5 uses)
        for i in range(3):
            store.add_trajectory(Trajectory("CompileService", "p", "HTN", success=False, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=1, recoveries_count=0, combined_score=0.0))

        res = SkillOptimizer.evaluate_and_evolve_skill("CompileService", store)
        assert res["success"] is True
        assert res["action"] == "skipped"

    def test_evaluate_demotes_trusted_skill(self):
        skill = SkillLibrary.add_skill(
            name="CompileService",
            description="Build steps",
            inputs=[],
            steps=["CompileNode"],
            outputs=[],
            tags=["build"]
        )
        
        # Manually promote to trusted (requires 3 successes with rate >= 0.8)
        for _ in range(3):
            SkillLibrary.record_result("CompileService", success=True)
        assert SkillLibrary.get("CompileService")["trust"] == "trusted"

        # Now simulate 5 failed runs
        store = ExperienceStore()
        for _ in range(5):
            store.add_trajectory(Trajectory("CompileService", "p", "HTN", success=False, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=1, recoveries_count=0, combined_score=0.0))

        res = SkillOptimizer.evaluate_and_evolve_skill("CompileService", store)
        assert res["success"] is True
        assert res["action"] == "demoted"
        assert res["trust"] == "draft"

    def test_compare_and_upgrade_steps_improvement(self):
        SkillLibrary.add_skill(
            name="DockerRun",
            description="Deploy docker",
            inputs=[],
            steps=["DockerPull", "DockerSpawn"],
            outputs=[],
            tags=["dev"]
        )

        # Baseline: success rate is not set -> default 75.0 score.
        # Variant shows 95.0 score -> Upgrade!
        res = SkillOptimizer.compare_and_upgrade_steps(
            skill_name="DockerRun",
            new_steps=["DockerPull", "DockerSpawn", "DockerVerify"],
            new_performance_score=95.0
        )

        assert res["success"] is True
        assert res["action"] == "upgraded"
        
        saved = SkillLibrary.get("DockerRun")
        assert "DockerVerify" in saved["steps"]

    def test_compare_and_upgrade_steps_no_improvement(self):
        SkillLibrary.add_skill(
            name="DockerRun",
            description="Deploy docker",
            inputs=[],
            steps=["DockerPull", "DockerSpawn"],
            outputs=[],
            tags=["dev"]
        )
        
        # Set success rate to 0.90 -> Baseline score = 90.0
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=True)
        SkillLibrary.record_result("DockerRun", success=False)  # 9/10 successes -> 90%

        # Variant score = 85.0 -> No upgrade!
        res = SkillOptimizer.compare_and_upgrade_steps(
            skill_name="DockerRun",
            new_steps=["DockerPull", "DockerSpawn", "DockerVerify"],
            new_performance_score=85.0
        )

        assert res["success"] is True
        assert res["action"] == "none"
        
        saved = SkillLibrary.get("DockerRun")
        assert "DockerVerify" not in saved["steps"]
