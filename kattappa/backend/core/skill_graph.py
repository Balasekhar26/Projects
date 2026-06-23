from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from backend.core.knowledge_graph import KnowledgeGraph


class SkillGraph:
    """Skill Graph Subsystem (Layer 8 - Step 8.4).

    Wraps the semantic Knowledge Graph to establish relations between executable
    skills, tool requirements, agent ownership, and procedural prerequisites.
    """

    @classmethod
    def register_skill(
        cls,
        skill_id: str,
        name: str,
        description: str,
        tools: List[str],
        agents: List[str],
        prerequisites: Optional[List[str]] = None,
    ) -> None:
        """Registers a procedural skill along with its agent, tool, and prerequisite dependencies."""
        # 1. Add skill node
        KnowledgeGraph.add_node(
            node_id=skill_id,
            node_type="skill",
            properties={"name": name, "description": description},
        )

        # 2. Add and link executing agents
        for agent in agents:
            KnowledgeGraph.add_node(node_id=agent, node_type="agent")
            KnowledgeGraph.add_edge(source_id=skill_id, target_id=agent, relation_type="EXECUTED_BY")

        # 3. Add and link required tools
        for tool in tools:
            KnowledgeGraph.add_node(node_id=tool, node_type="tool")
            KnowledgeGraph.add_edge(source_id=skill_id, target_id=tool, relation_type="REQUIRES_TOOL")

        # 4. Link prerequisite skills
        if prerequisites:
            for prereq in prerequisites:
                # Ensure the prerequisite node exists in case it wasn't registered yet
                prereq_node = KnowledgeGraph.get_node(prereq)
                if not prereq_node:
                    KnowledgeGraph.add_node(node_id=prereq, node_type="skill")
                KnowledgeGraph.add_edge(source_id=skill_id, target_id=prereq, relation_type="DEPENDS_ON")

    @classmethod
    def get_skill_details(cls, skill_id: str) -> Optional[Dict[str, Any]]:
        """Returns details, agents, tools, and prerequisites of a registered skill."""
        node = KnowledgeGraph.get_node(skill_id)
        if not node or node["type"] != "skill":
            return None

        neighbors = KnowledgeGraph.query_neighbors(skill_id, direction="out")
        agents = []
        tools = []
        prerequisites = []

        for nb in neighbors:
            rel = nb["relation"]
            if rel == "EXECUTED_BY":
                agents.append(nb["node_id"])
            elif rel == "REQUIRES_TOOL":
                tools.append(nb["node_id"])
            elif rel == "DEPENDS_ON":
                prerequisites.append(nb["node_id"])

        return {
            "skill_id": skill_id,
            "name": node["properties"].get("name", ""),
            "description": node["properties"].get("description", ""),
            "agents": agents,
            "tools": tools,
            "prerequisites": prerequisites,
        }

    @classmethod
    def get_skill_dependencies(cls, skill_id: str) -> List[str]:
        """Performs a depth-first search (DFS) topological sort to resolve a flat list of skill prerequisites."""
        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(node_id: str):
            visited.add(node_id)
            node_details = cls.get_skill_details(node_id)
            if node_details:
                for prereq in node_details["prerequisites"]:
                    if prereq not in visited:
                        dfs(prereq)
            stack.append(node_id)

        dfs(skill_id)
        # Prereqs are executed first, so they appear first in stack
        return stack

    @classmethod
    def find_skills_for_tool(cls, tool_name: str) -> List[str]:
        """Returns all skills that depend on a specific execution tool."""
        neighbors = KnowledgeGraph.query_neighbors(tool_name, direction="in", relation_type="REQUIRES_TOOL")
        return [nb["node_id"] for nb in neighbors if nb["type"] == "skill"]

    @classmethod
    def verify_skill_prerequisites_met(cls, skill_id: str, available_tools: List[str]) -> bool:
        """Verifies if the necessary tool dependencies for a skill are met in the current execution state."""
        details = cls.get_skill_details(skill_id)
        if not details:
            return False

        # Verify tool availability
        required_tools = set(details["tools"])
        available_set = set(available_tools)
        return required_tools.issubset(available_set)
