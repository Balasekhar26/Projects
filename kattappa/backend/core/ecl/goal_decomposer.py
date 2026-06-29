from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel
from backend.core.model_router import ask_model

logger = logging.getLogger(__name__)

_FALLBACK_SUBGOALS_TEMPLATE = [
    {
        "title": "Analyze requirements",
        "description": "Gather metrics and map context boundaries.",
        "tasks": [
            {
                "title": "Inspect baseline workspace environment",
                "description": "Identify configuration files and paths.",
            },
            {
                "title": "Formulate execution constraints",
                "description": "Calculate token, CPU, and latency limits.",
            },
        ],
    },
    {
        "title": "Execute core implementation",
        "description": "Write production code changes and verify functionality.",
        "tasks": [
            {
                "title": "Implement proposed changes",
                "description": "Modify target files as specified by plan.",
            },
            {
                "title": "Run automated test suites",
                "description": "Verify code builds and passes assertions.",
            },
        ],
    },
]


class ECLGoalDecomposer:
    """Decomposes Level 1 goals into Level 2 subgoals and Level 3 tasks inside GoalHierarchy."""

    @classmethod
    def decompose(
        cls,
        goal_title: str,
        goal_desc: str = "",
        goal_id: str | None = None,
    ) -> Dict[str, Any]:
        """Triggers the goal decomposition pipeline and registers all nodes in the database."""
        # 1. Generate/validate Goal ID
        g_id = goal_id or f"goal_{uuid.uuid4().hex[:8]}"

        # 2. Register Level 1 Goal Node
        GoalHierarchy.add_node(
            node_id=g_id,
            parent_id=None,
            level=HierarchyLevel.GOAL,
            title=goal_title,
            description=goal_desc,
            status="ACTIVE",
            progress=0.0,
        )

        # 3. Dynamic Model-driven decomposition with fallback
        subgoals_data: List[Dict[str, Any]] = []
        prompt = (
            "You are a goal decomposition assistant. Decompose this high-level goal into a structured JSON list of subgoals "
            "and their children tasks.\n"
            f"Goal: {goal_title}\nDescription: {goal_desc}\n\n"
            "Format the output strictly as a JSON list of objects, where each object has:\n"
            "- 'title': title of the subgoal\n"
            "- 'description': description of the subgoal\n"
            "- 'tasks': a list of objects, each representing a child task with 'title' and 'description'\n"
            "Do not include any explanation or markdown formatting, just the raw JSON array."
        )

        try:
            response = ask_model(prompt, role="general")
            clean_resp = response.strip()
            if clean_resp.startswith("```json"):
                clean_resp = clean_resp[7:]
            if clean_resp.endswith("```"):
                clean_resp = clean_resp[:-3]
            clean_resp = clean_resp.strip()
            parsed = json.loads(clean_resp)
            if isinstance(parsed, list) and parsed:
                subgoals_data = parsed
        except Exception as exc:
            logger.debug("Model decomposition failed or returned invalid JSON: %s", exc)

        # 4. Always fall back to baseline if model produced nothing useful
        if not subgoals_data:
            subgoals_data = _FALLBACK_SUBGOALS_TEMPLATE

        registered_nodes: List[Dict[str, Any]] = []

        # 5. Register Subgoals (Level 2) and Tasks (Level 3)
        for sg_idx, sg in enumerate(subgoals_data):
            sg_title = sg.get("title", f"Subgoal {sg_idx + 1}")
            sg_desc = sg.get("description", "")
            sg_id = f"{g_id}_sub_{sg_idx}"

            GoalHierarchy.add_node(
                node_id=sg_id,
                parent_id=g_id,
                level=HierarchyLevel.SUBGOAL,
                title=sg_title,
                description=sg_desc,
                status="PROPOSED",
                progress=0.0,
            )
            registered_nodes.append({"id": sg_id, "level": "SUBGOAL", "title": sg_title})

            tasks = sg.get("tasks", [])
            for t_idx, t in enumerate(tasks):
                t_title = t.get("title", f"Task {t_idx + 1}")
                t_desc = t.get("description", "")
                t_id = f"{sg_id}_task_{t_idx}"

                GoalHierarchy.add_node(
                    node_id=t_id,
                    parent_id=sg_id,
                    level=HierarchyLevel.TASK,
                    title=t_title,
                    description=t_desc,
                    status="PROPOSED",
                    progress=0.0,
                )
                registered_nodes.append({"id": t_id, "level": "TASK", "title": t_title})

        return {
            "goal_id": g_id,
            "title": goal_title,
            "registered_nodes": registered_nodes,
        }
