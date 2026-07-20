from collections import Counter

class PreferenceTracker:
    def __init__(self):
        self._preferences: list[dict] = []

    def record_preference(self, category: str, choice: str, weight: float = 1.0) -> None:
        """Records a user choice with an optional importance weight."""
        self._preferences.append({
            "category": category,
            "choice": choice,
            "weight": weight
        })

    def get_ranked_preferences(self, category: str) -> list[tuple[str, float]]:
        """Returns choices for a category ranked by cumulative weight (descending)."""
        weights: dict[str, float] = {}
        for p in self._preferences:
            if p["category"] == category:
                weights[p["choice"]] = weights.get(p["choice"], 0.0) + p["weight"]

        return sorted(weights.items(), key=lambda x: x[1], reverse=True)

    def get_top_preference(self, category: str) -> str | None:
        """Returns the single highest-weighted choice for a category, or None."""
        ranked = self.get_ranked_preferences(category)
        return ranked[0][0] if ranked else None
