from __future__ import annotations

from typing import Any, Dict, List, Optional
from backend.core.project_memory import ProjectMemory


class ProjectManagerV2:
    """Core logic coordinator for V2 Project Management (Step 8.2)."""

    @classmethod
    def create_project(
        cls,
        name: str,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates a new project profile."""
        return ProjectMemory.create_project(
            name=name,
            description=description,
            status=status,
            project_id=project_id,
            metadata=metadata,
        )

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a project."""
        return ProjectMemory.get_project(project_id)

    @classmethod
    def list_projects(cls) -> List[Dict[str, Any]]:
        """Lists all projects in the system."""
        return ProjectMemory.list_projects()

    @classmethod
    def add_goal_to_project(cls, goal_id: str, project_id: str) -> None:
        """Links a Goal to a Project."""
        ProjectMemory.associate_goal_to_project(goal_id, project_id)

    @classmethod
    def add_project_dependency(cls, project_id: str, depends_on_project_id: str) -> None:
        """Establishes project-level dependency mapping."""
        ProjectMemory.add_project_dependency(project_id, depends_on_project_id)

    @classmethod
    def update_project_status(cls, project_id: str, status: str) -> Dict[str, Any]:
        """Changes execution status state of a project."""
        return ProjectMemory.update_project_status(project_id, status)

    @classmethod
    def log_project_decision(
        cls,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> None:
        """Registers a project-level configuration decision."""
        ProjectMemory.log_project_decision(project_id, title, description, rationale)

    @classmethod
    def log_project_failure(cls, project_id: str, component: str, error_message: str) -> None:
        """Registers a project exception execution failure."""
        ProjectMemory.log_project_failure(project_id, component, error_message)

    @classmethod
    def log_project_rollback(
        cls,
        project_id: str,
        milestone_id: Optional[str],
        action_id: Optional[str],
        reason: str,
    ) -> None:
        """Registers a rollback operation event on a project."""
        ProjectMemory.log_project_rollback(project_id, milestone_id, action_id, reason)

    @classmethod
    def create_task(
        cls,
        task_id: str,
        milestone_id: str,
        title: str,
        description: Optional[str] = None,
        assigned_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a Task under a Milestone."""
        return ProjectMemory.create_task(
            task_id=task_id,
            milestone_id=milestone_id,
            title=title,
            description=description,
            assigned_agent=assigned_agent,
        )

    @classmethod
    def update_task_status(cls, task_id: str, status: str, progress: Optional[float] = None) -> Dict[str, Any]:
        """Updates task progress status."""
        return ProjectMemory.update_task_status(task_id, status, progress)

    @classmethod
    def create_action(
        cls,
        action_id: str,
        task_id: str,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "PROPOSED",
        result: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates an Action trace record under a task."""
        return ProjectMemory.create_action(
            action_id=action_id,
            task_id=task_id,
            action_type=action_type,
            payload=payload,
            status=status,
            result=result,
        )

    @classmethod
    def get_project_hierarchy(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """Compiles the complete execution hierarchy tree for a project: Project -> Goal -> Milestone -> Task -> Action."""
        project = ProjectMemory.get_project(project_id)
        if not project:
            return None

        # Build full goal tree
        from backend.core.goal_memory import GoalMemory
        tree_goals = []
        for g_summary in project["goals"]:
            goal = GoalMemory.get_goal(g_summary["goal_id"])
            if goal:
                milestones_tree = []
                for m in goal["milestones"]:
                    # Fetch tasks for this milestone
                    conn = ProjectMemory._get_sqlite_conn()
                    try:
                        trows = conn.execute("SELECT task_id FROM tasks WHERE milestone_id = ?", (m["milestone_id"],)).fetchall()
                        tasks = []
                        for tr in trows:
                            task = ProjectMemory.get_task(tr["task_id"])
                            if task:
                                # Fetch actions for this task
                                arows = conn.execute("SELECT action_id FROM actions WHERE task_id = ?", (tr["task_id"],)).fetchall()
                                actions = [ProjectMemory.get_action(ar["action_id"]) for ar in arows]
                                task["actions"] = [a for a in actions if a is not None]
                                tasks.append(task)
                        m["tasks"] = tasks
                    finally:
                        conn.close()
                    milestones_tree.append(m)
                goal["milestones"] = milestones_tree
                tree_goals.append(goal)

        project["goals_tree"] = tree_goals
        return project

    @classmethod
    def reset(cls) -> None:
        """Resets the project registry."""
        ProjectMemory.reset()
