"""Unit tests for Program 21.0: Offline Learning and Skill Formation Pipeline.

Verifies experience indexing, performance rankers, failure analyzers, and skill template formations.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from backend.core.learning.experience_store import ExperienceStore
from backend.core.learning.trajectory_builder import Trajectory
from backend.core.learning.experience_retrieval import ExperienceRetrieval
from backend.core.learning.performance_ranker import PerformanceRanker
from backend.core.learning.trajectory_analyzer import TrajectoryAnalyzer
from backend.core.learning.skill_former import SkillFormer
from backend.core.skill_library import SkillLibrary


@pytest.fixture(autouse=True)
def clean_skill_library():
    """Resets skill library config before and after tests."""
    SkillLibrary.reset()
    yield
    SkillLibrary.reset()


# ── 1. Experience Retrieval Similarity Tests ──────────────────────────────────

class TestExperienceRetrieval:
    def test_find_similar_experiences(self):
        store = ExperienceStore()
        
        t1 = Trajectory(
            goal_id="deploy-container-service",
            plan_id="p1",
            planner_version="HTN-1",
            success=True,
            predicted_duration=5.0,
            actual_duration=5.0,
            predicted_cost=0.5,
            actual_cost=0.5,
            failures_count=0,
            recoveries_count=0,
            combined_score=95.0,
            nodes_executed=["PullImage", "SpawnDocker", "VerifyService"]
        )

        t2 = Trajectory(
            goal_id="install-local-npm-package",
            plan_id="p2",
            planner_version="HTN-2",
            success=True,
            predicted_duration=10.0,
            actual_duration=12.0,
            predicted_cost=1.0,
            actual_cost=1.0,
            failures_count=0,
            recoveries_count=0,
            combined_score=85.0,
            nodes_executed=["RunCommand", "UpdatePackages"]
        )

        store.add_trajectory(t1)
        store.add_trajectory(t2)

        # Retrieve matching "container docker deploy" -> should match t1
        matches = ExperienceRetrieval.find_similar_experiences("container docker deploy", store)
        assert len(matches) == 1
        assert matches[0]["trajectory"].goal_id == "deploy-container-service"
        assert matches[0]["score"] > 0.0


# ── 2. Performance Ranker Tests ───────────────────────────────────────────────

class TestPerformanceRanker:
    def test_rank_planners(self):
        store = ExperienceStore()

        t1 = Trajectory("g1", "p1", "HTN-v1", success=True, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=0, combined_score=95.0)
        t2 = Trajectory("g2", "p2", "HTN-v1", success=False, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=1, recoveries_count=0, combined_score=40.0)
        t3 = Trajectory("g3", "p3", "HTN-v2", success=True, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=0, combined_score=98.0)

        store.add_trajectory(t1)
        store.add_trajectory(t2)
        # HTN-v1: 1 success, 1 fail -> 50% rate
        # HTN-v2: 1 success, 0 fail -> 100% rate
        store.add_trajectory(t3)

        ranks = PerformanceRanker.rank_planners(store)
        assert len(ranks) == 2
        assert ranks[0]["planner_version"] == "HTN-v2"
        assert ranks[0]["success_rate"] == 1.0
        assert ranks[1]["planner_version"] == "HTN-v1"
        assert ranks[1]["success_rate"] == 0.5


# ── 3. Trajectory Failure Analyzer Tests ──────────────────────────────────────

class TestTrajectoryAnalyzer:
    def test_compile_failure_diagnostics(self):
        store = ExperienceStore()
        
        # 2 failed runs. "DownloadRepo" fails in both
        t1 = Trajectory("g1", "p1", "HTN-1", success=False, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=1, recoveries_count=0, combined_score=0.0, nodes_executed=["failed:DownloadRepo"])
        t2 = Trajectory("g2", "p2", "HTN-1", success=False, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=1, recoveries_count=1, combined_score=0.0, nodes_executed=["VerifyPath", "failed:DownloadRepo"])
        t3 = Trajectory("g3", "p3", "HTN-1", success=True, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=0, combined_score=95.0, nodes_executed=["VerifyPath"])

        store.add_trajectory(t1)
        store.add_trajectory(t2)
        store.add_trajectory(t3)

        diagnostics = TrajectoryAnalyzer.compile_failure_diagnostics(store)
        assert diagnostics["total_failures"] == 2
        assert len(diagnostics["failure_hotspots"]) == 1
        assert diagnostics["failure_hotspots"][0]["node_title"] == "DownloadRepo"

        # Check dynamic warnings generation
        warnings = TrajectoryAnalyzer.generate_planning_warnings(store)
        assert len(warnings) == 1
        assert "DownloadRepo" in warnings[0]


# ── 4. Skill Former Distillation Tests ────────────────────────────────────────

class TestSkillFormer:
    def test_distill_trajectory_to_skill(self):
        t = Trajectory(
            goal_id="g1",
            plan_id="p123",
            planner_version="HTN-1",
            success=True,
            predicted_duration=5,
            actual_duration=5,
            predicted_cost=1,
            actual_cost=1,
            failures_count=0,
            recoveries_count=0,
            combined_score=98.0,
            nodes_executed=["SetupEnv", "failed:InstallPackage", "VerifyInstall"]
        )

        res = SkillFormer.distill_trajectory_to_skill(t, "DistilledSkill", description="Mock skill")
        assert res["success"] is True
        
        # Verify it was saved inside persistent library
        saved = SkillLibrary.get("DistilledSkill")
        assert saved is not None
        assert saved["name"] == "DistilledSkill"
        # Steps should exclude failed tags
        assert "SetupEnv" in saved["steps"]
        assert "VerifyInstall" in saved["steps"]
        assert "failed:InstallPackage" not in saved["steps"]

    def test_auto_promotion(self):
        store = ExperienceStore()
        
        t_high = Trajectory("g1", "high-plan", "HTN-1", success=True, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=0, combined_score=95.0, nodes_executed=["NodeA"])
        t_low = Trajectory("g2", "low-plan", "HTN-1", success=True, predicted_duration=1, actual_duration=1, predicted_cost=1, actual_cost=1, failures_count=0, recoveries_count=0, combined_score=80.0, nodes_executed=["NodeB"])

        store.add_trajectory(t_high)
        store.add_trajectory(t_low)

        promoted = SkillFormer.run_auto_promotion(store, score_threshold=90.0)
        # Only t_high is above 90 -> promoted
        assert len(promoted) == 1
        assert "high-plan" in promoted[0]["name"]
