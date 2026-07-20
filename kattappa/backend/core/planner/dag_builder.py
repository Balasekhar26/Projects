from __future__ import annotations

class DAGBuilder:
    @classmethod
    def validate_and_order(cls, steps: list[dict]) -> list[dict]:
        """Validates that planning steps contain no circular dependencies and orders them topologically."""
        adj = {}
        in_degree = {}
        for s in steps:
            sid = s["step_id"]
            adj[sid] = []
            in_degree[sid] = 0
            
        for s in steps:
            sid = s["step_id"]
            for dep in s.get("dependencies", []):
                if dep in adj:
                    adj[dep].append(sid)
                    in_degree[sid] += 1
                    
        # Kahn's Algorithm
        queue = [sid for sid in adj if in_degree[sid] == 0]
        ordered = []
        while queue:
            curr = queue.pop(0)
            ordered.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    
        if len(ordered) != len(steps):
            raise ValueError("Cyclic dependencies detected in generated planner steps!")
            
        step_map = {s["step_id"]: s for s in steps}
        return [step_map[sid] for sid in ordered]
