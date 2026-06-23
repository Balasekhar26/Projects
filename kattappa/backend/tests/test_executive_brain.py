import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.mission_memory import MissionMemory
from backend.core.mission_manager import MissionManager
from backend.core.self_evaluator import SelfEvaluator
from backend.core.learning_dashboard import LearningDashboard


@pytest.fixture(autouse=True)
def mock_persistent_paths(monkeypatch, tmp_path):
    # Route all JSON file paths to temp directories during tests
    monkeypatch.setattr("backend.core.mission_memory._mission_file_path", lambda: tmp_path / "mission_memory.json")
    monkeypatch.setattr("backend.core.self_evaluator._eval_file_path", lambda: tmp_path / "self_evaluations.json")


def test_mission_memory_seeding_and_crud():
    missions = MissionMemory.load_missions()
    assert "mis_drone_jam" in missions
    assert missions["mis_drone_jam"]["title"] == "Drone Jammer Design"
    
    # Add new mission
    new_mission = {
        "id": "mis_test",
        "title": "Test Mission",
        "description": "Test description",
        "stages": ["Step1", "Step2"],
        "current_stage": "Step1",
        "status": "running",
        "created_at": 100.0,
        "completed_at": None,
        "lessons_learned": [],
        "user_project": "Test Project"
    }
    MissionMemory.add_mission(new_mission)
    
    retrieved = MissionMemory.get_mission("mis_test")
    assert retrieved is not None
    assert retrieved["title"] == "Test Mission"
    
    # Update status
    MissionMemory.update_mission_status("mis_test", "completed", current_stage="Step2")
    retrieved_updated = MissionMemory.get_mission("mis_test")
    assert retrieved_updated["status"] == "completed"
    assert retrieved_updated["current_stage"] == "Step2"
    assert retrieved_updated["completed_at"] is not None
    
    # Add lesson
    MissionMemory.add_lesson("mis_test", "Always test clean directories.")
    assert "Always test clean directories." in MissionMemory.get_mission("mis_test")["lessons_learned"]


def test_goal_engine_stage_routing():
    # Software goal routing
    sw_mission = MissionManager.create_mission_from_goal("Build REST API backend", "Use Python and FastAPI.")
    assert sw_mission["stages"] == ["Requirements", "Architecture", "Implementation", "Testing", "Deployment"]
    
    # Hardware/RF routing
    hw_mission = MissionManager.create_mission_from_goal("Analyze RF sensor signals", "Use hardware spectrum analyzer.")
    assert hw_mission["stages"] == ["Research", "Design", "Simulation", "Testing", "Documentation"]
    
    # Default routing
    def_mission = MissionManager.create_mission_from_goal("Clean up workspace files", "General tidy up.")
    assert def_mission["stages"] == ["Research", "Plan", "Execute", "Verify", "Report"]


def test_long_horizon_planning():
    plan_embedded = MissionManager.generate_long_horizon_plan("Embedded systems developer roadmap")
    assert "STM32" in plan_embedded["today"]
    assert "RTOS" in plan_embedded["this_quarter"]["Month 2"]
    
    plan_general = MissionManager.generate_long_horizon_plan("General software roadmap")
    assert "specifications" in plan_general["today"].lower()


def test_strategic_planning_engine():
    # Negative scan (no keyword match)
    rec_none = MissionManager.scan_for_strategic_projects("No major updates in embedded space today.")
    assert rec_none is None
    
    # Positive scan (triggers automated proposal/mission launch)
    rec_active = MissionManager.scan_for_strategic_projects("A new RF chipset has been released by STMicroelectronics.")
    assert rec_active is not None
    assert rec_active["project_title"] == "Low-cost jammer development"
    
    # Make sure it actually launched the mission in memory
    missions = MissionMemory.load_missions()
    assert any(m["title"] == "Low-cost jammer development" for m in missions.values())


def test_self_evaluator_metrics():
    evals = SelfEvaluator.load_evaluations()
    assert len(evals) == 2
    assert evals[0]["agent"] == "Coder"
    
    # Add evaluation
    SelfEvaluator.add_evaluation(
        agent="Coder",
        plan_score=95,
        execution_score=90,
        accuracy_score=100,
        cost_score=85,
        time_score=80,
        what_worked="Refactoring compiled immediately.",
        what_failed="Mock API tests had minor delay.",
        improvement="Optimized test suite parallelization."
    )
    
    averages = SelfEvaluator.agent_performance_averages()
    # Averages should reflect the newly added evaluation
    assert averages["Coder"]["plan"] > 88.0


def test_learning_dashboard_executive_stats():
    # Set up some dummy data
    MissionManager.create_mission_from_goal("Drone Jammer Design", "RF jammer module", "Drone Jammer Project")
    SelfEvaluator.add_evaluation("Browser", 85, 90, 85, 90, 80, "Worked", "Failed", "Improve")
    
    stats = LearningDashboard.executive_brain_stats()
    assert stats["counts"]["running"] >= 1
    assert "Browser" in stats["performance"]
    assert len(stats["weekly_trend"]) == 5
    assert len(stats["long_horizon"]["today"]) > 0


def test_executive_brain_api_endpoints():
    client = TestClient(app)
    
    # 1. Test GET /dashboard/executive-brain/missions
    resp1 = client.get("/dashboard/executive-brain/missions")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "ok"
    assert "missions" in data1["data"]
    assert "long_horizon" in data1["data"]
    
    # 2. Test POST /dashboard/executive-brain/missions/create
    resp2 = client.post("/dashboard/executive-brain/missions/create", json={
        "title": "Build Autonomous Drone Jammer",
        "description": "Construct high-gain RF output stage."
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "ok"
    assert data2["data"]["title"] == "Build Autonomous Drone Jammer"
    assert "Simulation" in data2["data"]["stages"]
    
    # 3. Test GET /dashboard/executive-brain/evaluations
    resp3 = client.get("/dashboard/executive-brain/evaluations")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["status"] == "ok"
    assert "evaluations" in data3["data"]
    assert "performance" in data3["data"]
