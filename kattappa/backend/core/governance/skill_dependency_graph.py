from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parses a version string like '1.2.3' into a tuple of integers."""
    return tuple(map(int, re.findall(r"\d+", version_str)))


def compare_versions(v1: str, op: str, v2: str) -> bool:
    """Compares version v1 against constraint v2 using operation op."""
    try:
        t1 = parse_version(v1)
        t2 = parse_version(v2)
        if op == ">=":
            return t1 >= t2
        elif op == "<=":
            return t1 <= t2
        elif op == ">":
            return t1 > t2
        elif op == "<":
            return t1 < t2
        else:
            return t1 == t2
    except Exception:
        return False


def verify_dependencies(skill_name: str, active_skills: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Verifies that all dependency constraints are met for a skill and checks for circular dependencies."""
    skills_map = {s["name"]: s for s in active_skills}
    if skill_name not in skills_map:
        return False, f"Skill '{skill_name}' is not registered."

    # Circular dependency detection via DFS
    visited = {}  # name -> state (0 = visiting, 1 = visited)
    
    def dfs(node: str) -> Tuple[bool, str]:
        if node not in skills_map:
            return False, f"Missing dependency: '{node}'."
            
        visited[node] = 0  # visiting
        skill_info = skills_map[node]
        
        for dep in skill_info.get("dependencies", []):
            dep_name = dep["name"]
            dep_constraint = dep["version"]
            
            # Check version constraint
            if dep_name not in skills_map:
                return False, f"Missing dependency '{dep_name}' required by '{node}'."
                
            dep_skill = skills_map[dep_name]
            v_match = re.match(r"(>=|<=|>|<|==)?\s*(.*)", dep_constraint)
            if v_match:
                op, v_req = v_match.groups()
                op = op or "=="
                if not compare_versions(dep_skill["version"], op, v_req):
                    return False, f"Version mismatch: '{dep_name}' version {dep_skill['version']} does not satisfy constraint '{dep_constraint}' required by '{node}'."
            
            # Detect circular reference
            if visited.get(dep_name) == 0:
                return False, f"Circular dependency detected containing '{node}' and '{dep_name}'."
            if dep_name not in visited:
                ok, err = dfs(dep_name)
                if not ok:
                    return False, err
                    
        visited[node] = 1  # visited
        return True, "VERIFIED"

    return dfs(skill_name)
