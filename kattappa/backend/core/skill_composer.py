"""Skill Composer (Program 56.0).

Constructs executable ComposedSkill directed acyclic execution graphs from simpler,
discovered skills. Handles dependency sorting, cycle detection, parallel execution opportunities,
critical-path latency/cost estimation, and fallback plan bindings.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set


class ComposedSkill:
    """Represents a compiled, composed execution graph of constituent skills."""

    def __init__(
        self,
        name: str,
        description: str,
        constituent_skills: List[Dict[str, Any]],
        dependency_graph: Dict[str, List[str]],
        fallback_plan: Dict[str, str],
        estimated_cost: Dict[str, Any],
        execution_plan: List[List[str]],
    ) -> None:
        self.name = name.strip()
        self.description = description.strip()
        self.constituent_skills = constituent_skills
        self.dependency_graph = dependency_graph
        self.fallback_plan = fallback_plan
        self.estimated_cost = estimated_cost
        self.execution_plan = execution_plan


class SkillComposer:
    """Compiles multiple constituent skills into an execution plan graph."""

    @classmethod
    def compose_skills(
        cls,
        name: str,
        description: str,
        skills: List[Dict[str, Any]],
        dependencies: Dict[str, List[str]],
        fallbacks: Dict[str, str] | None = None,
    ) -> ComposedSkill:
        name = name.strip()
        if not name:
            raise ValueError("Composed skill name cannot be empty")

        fallbacks = fallbacks or {}

        # 1. Validation: check that all skill names referenced in graphs exist
        skill_names = {s["name"] for s in skills}
        for node, deps in dependencies.items():
            if node not in skill_names:
                raise ValueError(f"Constituent skill {node!r} referenced in dependencies is missing from skills list")
            for d in deps:
                if d not in skill_names:
                    raise ValueError(f"Dependency skill {d!r} referenced by {node!r} is missing from skills list")
        for node, fallback in fallbacks.items():
            if node not in skill_names:
                raise ValueError(f"Constituent skill {node!r} referenced in fallbacks is missing from skills list")
            if fallback not in skill_names:
                raise ValueError(f"Fallback skill {fallback!r} referenced by {node!r} is missing from skills list")

        # 2. Cycle Detection (DFS traversal)
        # dependency -> node indicates order of execution. So edges are: d -> node
        adj: Dict[str, List[str]] = {s["name"]: [] for s in skills}
        for node, deps in dependencies.items():
            for d in deps:
                adj[d].append(node)

        visiting: Set[str] = set()
        visited: Set[str] = set()

        def has_cycle(node: str) -> bool:
            visiting.add(node)
            for neighbor in adj[node]:
                if neighbor in visiting:
                    return True
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
            visiting.remove(node)
            visited.add(node)
            return False

        for skill_node in adj:
            if skill_node not in visited:
                if has_cycle(skill_node):
                    raise ValueError("Cyclic dependency detected")

        # 3. Parallel Layer Partitioning (Kahn's Topological Layer Sort)
        # Map node to the set of node names it depends on
        remaining_deps: Dict[str, Set[str]] = {s["name"]: set(dependencies.get(s["name"], [])) for s in skills}
        execution_plan: List[List[str]] = []

        while remaining_deps:
            # Current layer contains all remaining nodes with 0 outstanding dependencies
            layer = [node for node, deps in remaining_deps.items() if not deps]
            if not layer:
                # Fallback safeguard for cycles, though DFS cycle detection should have caught this
                raise ValueError("Graph contains unresolved cycles")

            # Add sorted layer to execution plan for deterministic outputs
            execution_plan.append(sorted(layer))

            # Remove layer nodes and clear dependencies of remaining nodes
            for node in layer:
                del remaining_deps[node]

            for node in remaining_deps:
                remaining_deps[node] = remaining_deps[node] - set(layer)

        # 4. Cost and Latency Estimation
        # Profile lookup values
        latency_map = {"low": 10.0, "medium": 30.0, "high": 90.0}
        cost_map = {"low": 1.0, "medium": 5.0, "high": 15.0}

        skills_by_name = {s["name"]: s for s in skills}
        total_cost = 0.0
        critical_path_latency = 0.0

        for s in skills:
            profile = s.get("cost_profile") or "low"
            total_cost += cost_map.get(profile, 1.0)

        # Total latency of parallel execution is the sum of maximum latency of each sequential layer
        for layer in execution_plan:
            layer_max_latency = 0.0
            for node_name in layer:
                s = skills_by_name[node_name]
                profile = s.get("cost_profile") or "low"
                layer_max_latency = max(layer_max_latency, latency_map.get(profile, 10.0))
            critical_path_latency += layer_max_latency

        estimated_cost = {
            "total_cost": round(total_cost, 2),
            "critical_path_latency": round(critical_path_latency, 2),
        }

        return ComposedSkill(
            name=name,
            description=description,
            constituent_skills=skills,
            dependency_graph=dependencies,
            fallback_plan=fallbacks,
            estimated_cost=estimated_cost,
            execution_plan=execution_plan,
        )
