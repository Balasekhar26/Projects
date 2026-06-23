from __future__ import annotations

import json
import time
import re
from typing import Any

from backend.core.capability_registry import (
    CapabilityRegistry,
    CAP_GOAL_MANAGE,
    CAP_GOAL_SCHEDULE,
)
from backend.core.goal_manager import GoalManager, GoalStatus
from backend.core.goal_memory import GoalMemory
from backend.core.simulation_engine import SimulationEngine


class ExecutiveAgent:
    def __init__(self) -> None:
        pass

    @classmethod
    def decompose_goal(cls, goal: str, agent_name: str = "executive") -> dict[str, Any]:
        """Decomposes a high-level goal into structured milestones, saving to GoalMemory SQLite."""
        if not CapabilityRegistry.is_capability_allowed(agent_name, CAP_GOAL_MANAGE):
            return {
                "success": False,
                "error": f"Security Error: Agent '{agent_name}' does not have CAP_GOAL_MANAGE capability."
            }

        lower_goal = goal.lower().strip()
        milestones = []

        if "rf" in lower_goal:
            milestones = [
                {"title": "Research RF engineering core concepts and fundamentals", "weight": 1.0, "description": "Fundamentals of RF design"},
                {"title": "Compile list of key RF design frameworks and software simulators", "weight": 1.0, "description": "Software simulation environments"},
                {"title": "Develop a learning pathway plan for antenna design", "weight": 1.0, "description": "Antenna path planning"}
            ]
        elif "chat" in lower_goal or "app" in lower_goal:
            milestones = [
                {"title": "Design the React frontend architecture for the chat application", "weight": 1.0, "description": "React layout"},
                {"title": "Implement the FastAPI backend WebSocket endpoints", "weight": 1.0, "description": "WebSockets"},
                {"title": "Set up SQLite database and integrate memory state validation", "weight": 1.0, "description": "SQLite and integrity"}
            ]
        else:
            try:
                from backend.core.model_router import ask_model
                prompt = (
                    f"Decompose the high-level goal: '{goal}' into a JSON array of milestones. "
                    "Each milestone must have: 'title' (string), 'weight' (float, e.g. 1.0), "
                    "'description' (string).\n"
                    "Output ONLY the raw JSON array. Example:\n"
                    '[{"title": "Step one", "weight": 1.0, "description": "Initialize framework"}]'
                )
                res = ask_model(prompt, role="fast")
                clean_res = res.strip()
                if clean_res.startswith("```json"):
                    clean_res = clean_res[7:]
                if clean_res.endswith("```"):
                    clean_res = clean_res[:-3]
                clean_res = clean_res.strip()
                milestones = json.loads(clean_res)
            except Exception:
                milestones = [
                    {"title": f"Phase 1: Initialize {goal}", "weight": 1.0, "description": "Initial setup"},
                    {"title": f"Phase 2: Complete {goal}", "weight": 1.0, "description": "Execution and completion"}
                ]

        # Insert high-level goal as PROPOSED first to generate goal_id
        goal_record = GoalManager.add_goal(
            title=goal,
            description=f"Decomposed goal: {goal}",
            priority="MEDIUM"
        )

        # Map list to structure with globally unique milestone IDs
        db_milestones = []
        for index, m in enumerate(milestones):
            m_id = f"{goal_record['goal_id']}_m{index + 1}"
            db_milestones.append({
                "milestone_id": m_id,
                "title": m["title"],
                "description": m.get("description", ""),
                "weight": m.get("weight", 1.0),
            })

        # Add the milestones
        GoalManager.add_milestones(goal_record["goal_id"], db_milestones)

        # Transition to ACTIVE
        GoalManager.start(goal_record["goal_id"])

        # Retrieve full details
        updated_goal = GoalManager.get(goal_record["goal_id"])
        
        # Add compatibility fields
        cls._add_compatibility_fields(updated_goal)
        
        return {"success": True, "goal_data": updated_goal}

    @classmethod
    def _add_compatibility_fields(cls, goal_data: dict[str, Any] | None) -> None:
        if not goal_data:
            return
        # map ACTIVE to IN_PROGRESS for tests
        if goal_data["status"] == "ACTIVE":
            goal_data["status"] = "IN_PROGRESS"
        
        for m in goal_data.get("milestones", []):
            m["id"] = m["milestone_id"].split("_")[-1] if "_" in m["milestone_id"] else m["milestone_id"]
            # map PENDING to PROPOSED
            if m["status"] == "PROPOSED":
                m["status"] = "PENDING"

    @classmethod
    def get_next_milestone(cls, goal_data: dict[str, Any]) -> dict[str, Any] | None:
        """Returns the highest priority proposed or pending milestone."""
        pending = [m for m in goal_data.get("milestones", []) if m["status"] in {"PROPOSED", "PENDING", "ACTIVE"}]
        if not pending:
            return None
        # Retrieve next milestone
        return pending[0]

    @classmethod
    def update_milestone_status(
        cls, goal_data: dict[str, Any], milestone_id: str, status: str
    ) -> dict[str, Any]:
        """Updates status of a milestone and overall goal status in GoalMemory."""
        # Map COMPLETED / PENDING
        status_clean = status.upper().strip()
        if status_clean == "PENDING":
            status_clean = "PROPOSED"

        full_id = milestone_id
        if "_" not in milestone_id:
            full_id = f"{goal_data['goal_id']}_{milestone_id}"

        GoalMemory.update_milestone(full_id, status=status_clean)
        
        # Reload full details
        updated_goal = GoalManager.get(goal_data["goal_id"])
        cls._add_compatibility_fields(updated_goal)
        return {"success": True, "goal_data": updated_goal}


def executive_node(state: dict[str, Any]) -> dict[str, Any]:
    user_input = state["user_input"]
    lower_input = user_input.lower().strip()
    logs = state.setdefault("logs", [])

    # 1. Check if request is a goal status query
    if any(kw in lower_input for kw in ("show goal", "check goal", "goal status", "check milestone")):
        if not CapabilityRegistry.is_capability_allowed("executive", CAP_GOAL_SCHEDULE):
            state["result"] = "Security Error: Agent 'executive' is blocked from scheduling/checking goals."
            return state

        goals = GoalManager.list_goals()
        if not goals:
            state["result"] = "No active goals found in database."
            return state

        short_lines = []
        for g in goals:
            # Map ACTIVE to IN_PROGRESS for print compatibility
            status = "IN_PROGRESS" if g["status"] == "ACTIVE" else g["status"]
            short_lines.append(f"Goal: {g['title']}")
            short_lines.append(f"Overall Status: {status}")
            short_lines.append(f"Priority Score: {g.get('priority_score', 1.0)}")
            short_lines.append("Milestones:")
            for m in g["milestones"]:
                m_status = "PENDING" if m["status"] == "PROPOSED" else m["status"]
                short_lines.append(f"  [{m_status}] {m['title']} (Priority: 1)")
        
        state["result"] = "\n".join(short_lines)
        logs.append("executive: recalled and reported goal status")
        return state

    # 1.1 Check if request is to execute the next milestone of the highest priority project/goal
    if any(kw in lower_input for kw in ("run next milestone", "execute next milestone", "continue execution", "run next step")):
        from backend.core.project_manager_v2 import ProjectManagerV2
        from backend.core.project_memory import ProjectMemory

        projects = ProjectManagerV2.list_projects()
        active_projects = [p for p in projects if p["status"] in {"ACTIVE", "APPROVED"}]
        active_projects.sort(key=lambda p: (0 if p["status"] == "ACTIVE" else 1, p["created_at"]))

        selected_goal = None
        selected_project = None

        for proj in active_projects:
            unmet_proj_deps = []
            for dep_id in proj.get("dependencies", []):
                dep_proj = ProjectManagerV2.get_project(dep_id)
                if dep_proj and dep_proj["status"] != "COMPLETED":
                    unmet_proj_deps.append(dep_proj["name"])

            if unmet_proj_deps:
                logs.append(f"executive: WARNING: Project '{proj['name']}' is blocked by delayed project(s): {unmet_proj_deps}")
                continue

            tree = ProjectManagerV2.get_project_hierarchy(proj["project_id"])
            if tree and tree.get("goals_tree"):
                sorted_goals = sorted(tree["goals_tree"], key=lambda g: g.get("priority_score", 0.0), reverse=True)
                for g in sorted_goals:
                    if g["status"] in {"ACTIVE", "APPROVED"}:
                        selected_goal = g
                        selected_project = proj
                        break
            if selected_goal:
                break

        if not selected_goal:
            active_goals = GoalManager.list_goals(status="ACTIVE")
            if not active_goals:
                active_goals = GoalManager.list_goals(status="APPROVED")
            if active_goals:
                selected_goal = active_goals[0]

        if not selected_goal:
            state["result"] = "No active or approved projects or goals found to execute."
            return state

        top_goal = selected_goal
        next_m = ExecutiveAgent.get_next_milestone(top_goal)
        if not next_m:
            state["result"] = f"All milestones completed for the highest priority goal '{top_goal['title']}'."
            return state

        if selected_project:
            logs.append(f"executive: selected project '{selected_project['name']}' -> goal '{top_goal['title']}' (Score: {top_goal.get('priority_score', 1.0)})")
        else:
            logs.append(f"executive: selected goal '{top_goal['title']}' (Score: {top_goal.get('priority_score', 1.0)})")
            
        logs.append(f"executive: scheduling milestone: {next_m['title']}")

        # Run milestone-level simulation
        try:
            sim_metrics = SimulationEngine.simulate_milestone(top_goal["goal_id"], next_m["milestone_id"])
            logs.append(f"executive: simulated milestone '{next_m['title']}' - success prob: {sim_metrics['success_probability']}, rollback: {sim_metrics['rollback_risk']}")
        except Exception as e:
            logs.append(f"executive: simulation failed: {e}")

        # Transition state to start milestone execution via planner
        state["user_input"] = next_m["title"]
        state["selected_agent"] = "planner"
        state["logs"].append(f"executive: routing first milestone '{next_m['title']}' to planner")
        return state

    # 2. Check if the user request is a high-level learning or development goal
    is_high_level_goal = any(
        phrase in lower_input
        for phrase in ("learn rf", "build a chat", "implement a system", "design a framework")
    )

    if is_high_level_goal:
        if not CapabilityRegistry.is_capability_allowed("executive", CAP_GOAL_MANAGE):
            state["result"] = "Security Error: Agent 'executive' does not have CAP_GOAL_MANAGE capability."
            return state

        res = ExecutiveAgent.decompose_goal(user_input, "executive")
        if not res.get("success"):
            state["result"] = res.get("error")
            return state

        goal_data = res["goal_data"]
        next_m = ExecutiveAgent.get_next_milestone(goal_data)

        if next_m:
            logs.append(f"executive: decomposed goal '{user_input}' into milestones")
            logs.append(f"executive: scheduling first milestone: {next_m['title']}")

            # Run milestone-level simulation
            try:
                sim_metrics = SimulationEngine.simulate_milestone(goal_data["goal_id"], next_m["milestone_id"])
                logs.append(f"executive: simulated milestone '{next_m['title']}' - success prob: {sim_metrics['success_probability']}, rollback: {sim_metrics['rollback_risk']}")
            except Exception as e:
                logs.append(f"executive: simulation failed: {e}")

            # Transition state to start milestone execution via planner
            state["user_input"] = next_m["title"]
            state["selected_agent"] = "planner"
            state["logs"].append(f"executive: routing first milestone '{next_m['title']}' to planner")

        return state

    # Pass-through for general requests
    logs.append("executive: pass-through to specialist agents")
    return state
