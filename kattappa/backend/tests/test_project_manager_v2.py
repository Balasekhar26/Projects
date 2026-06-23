from __future__ import annotations

import time
import pytest
from backend.core.project_manager_v2 import ProjectManagerV2
from backend.core.project_memory import ProjectMemory
from backend.core.goal_manager import GoalManager
from backend.core.goal_memory import GoalMemory
from backend.core.simulation_engine import SimulationEngine


@pytest.fixture(autouse=True)
def clean_db():
    ProjectManagerV2.reset()
    GoalManager.reset()
    yield
    ProjectManagerV2.reset()
    GoalManager.reset()


def test_project_creation_and_retrieval():
    # 1. Test create project
    proj = ProjectManagerV2.create_project(
        name="Cognitive Test Project",
        description="A project to test multi-agent OS logic",
        status="PROPOSED",
        metadata={"domain": "testing"}
    )
    assert proj["name"] == "Cognitive Test Project"
    assert proj["status"] == "PROPOSED"
    assert proj["metadata"]["domain"] == "testing"
    assert proj["completion_percent"] == 0.0

    # 2. Retrieve project
    retrieved = ProjectManagerV2.get_project(proj["project_id"])
    assert retrieved is not None
    assert retrieved["name"] == "Cognitive Test Project"

    # 3. List projects
    plist = ProjectManagerV2.list_projects()
    assert len(plist) == 1
    assert plist[0]["project_id"] == proj["project_id"]


def test_goal_association_and_metrics_cascading():
    proj = ProjectManagerV2.create_project(name="App Builder Project")
    p_id = proj["project_id"]

    # Create two goals
    g1 = GoalManager.add_goal(title="Goal 1", importance=6.0, resource_cost=2.0)
    g2 = GoalManager.add_goal(title="Goal 2", importance=8.0, resource_cost=4.0)

    # Associate goals to project
    ProjectManagerV2.add_goal_to_project(g1["goal_id"], p_id)
    ProjectManagerV2.add_goal_to_project(g2["goal_id"], p_id)

    # Check project retrieval has both goals
    p = ProjectManagerV2.get_project(p_id)
    assert len(p["goals"]) == 2
    assert p["completion_percent"] == 0.0

    # Add milestones and simulate to update goal progress & project success rates
    m1 = [{"milestone_id": "m1", "title": "Milestone 1", "weight": 1.0}]
    m2 = [{"milestone_id": "m2", "title": "Milestone 2", "weight": 1.0}]
    GoalManager.add_milestones(g1["goal_id"], m1)
    GoalManager.add_milestones(g2["goal_id"], m2)

    # Update milestone 1 progress
    GoalMemory.update_milestone("m1", progress=0.5, success_probability=0.8, rollback_risk=0.1)
    GoalMemory.update_milestone("m2", progress=1.0, status="COMPLETED", success_probability=0.9, rollback_risk=0.2)

    # Reload project metrics
    p_updated = ProjectManagerV2.get_project(p_id)
    # goal 1: progress 0.5; goal 2: progress 1.0 (completed)
    # average progress: (0.5 + 1.0) / 2 = 0.75
    assert p_updated["completion_percent"] == 0.75
    # success rate average of milestone 1 & 2: (0.8 + 0.9) / 2 = 0.85
    assert p_updated["success_rate"] == 0.85
    # risk score average: (0.1 + 0.2) / 2 = 0.15
    assert p_updated["risk_score"] == 0.15


def test_project_dependencies_and_cycle_prevention():
    p1 = ProjectManagerV2.create_project(name="Proj 1")
    p2 = ProjectManagerV2.create_project(name="Proj 2")
    p3 = ProjectManagerV2.create_project(name="Proj 3")

    # Establish sequence: P1 -> P2 -> P3
    ProjectManagerV2.add_project_dependency(p2["project_id"], p1["project_id"])
    ProjectManagerV2.add_project_dependency(p3["project_id"], p2["project_id"])

    # Attempting to create P1 -> P3 should be fine
    ProjectManagerV2.add_project_dependency(p3["project_id"], p1["project_id"])
    
    # Attempting to add P3 depends on P1 should trigger a cycle error because P2 depends on P1 and P3 depends on P2,
    # wait! Let's check: P2 depends on P1, P3 depends on P2. So P1 -> P2 -> P3.
    # If we add P1 depends on P3, then P1 depends on P3, which depends on P2, which depends on P1. This forms a cycle P1 -> P2 -> P3 -> P1!
    # Let's verify cycle prevention on that:
    with pytest.raises(ValueError, match="cycle"):
        ProjectManagerV2.add_project_dependency(p1["project_id"], p2["project_id"])


def test_project_simulation():
    proj = ProjectManagerV2.create_project(name="Simulated Project")
    p_id = proj["project_id"]

    g1 = GoalManager.add_goal(title="Research RF Engineering fundamentals")
    g2 = GoalManager.add_goal(title="Code Spectrum Analyzer App")
    ProjectManagerV2.add_goal_to_project(g1["goal_id"], p_id)
    ProjectManagerV2.add_goal_to_project(g2["goal_id"], p_id)

    # Add milestones
    m1 = [{"milestone_id": "m1", "title": "Research RF Fundamentals milestone", "weight": 1.0}]
    m2 = [{"milestone_id": "m2", "title": "Write Spectrum Analyzer React frontend milestone", "weight": 1.0}]
    GoalManager.add_milestones(g1["goal_id"], m1)
    GoalManager.add_milestones(g2["goal_id"], m2)

    # Set dependency between goals
    GoalMemory.add_dependency(g2["goal_id"], g1["goal_id"])

    # Run simulation
    report = SimulationEngine.simulate_project(p_id)
    assert "completion_probability" in report
    assert "predicted_finish_date" in report
    assert "critical_path" in report
    assert "resource_demand" in report
    
    # Critical path should include both milestones because goal 2 depends on goal 1
    assert len(report["critical_path"]) == 2
    # Verify coder resource load exists since milestone 2 has "write" in its title
    assert "coder" in report["resource_demand"]
