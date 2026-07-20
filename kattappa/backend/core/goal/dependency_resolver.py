class DependencyResolver:
    @classmethod
    def resolve_execution_order(cls, dependencies: dict[str, list[str]]) -> list[str]:
        """Resolves topological order for subgoals. Raises ValueError on dependency cycles."""
        visited = {} # None = unvisited, False = visiting, True = visited
        order = []

        def dfs(node: str):
            if visited.get(node) is False:
                raise ValueError("Cycle detected in subgoal dependencies")
            if visited.get(node) is True:
                return

            visited[node] = False
            for dep in dependencies.get(node, []):
                dfs(dep)
            visited[node] = True
            order.append(node)

        for node in dependencies:
            if node not in visited:
                dfs(node)

        return order
