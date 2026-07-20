class StrategyEvaluator:
    @classmethod
    def score_strategy(cls, success_rate: float, est_execution_time: float) -> float:
        """Scores a planning candidate strategy using historical success rates and runtime estimations."""
        # 70% weight on success, 30% weight on execution efficiency
        efficiency = 1.0 / (est_execution_time + 1.0)
        return float((0.7 * success_rate) + (0.3 * efficiency))

    @classmethod
    def select_best_strategy(cls, candidates: list[dict]) -> str | None:
        """Selects the highest scoring planning strategy from a list of candidates."""
        if not candidates:
            return None
            
        scored = []
        for c in candidates:
            score = cls.score_strategy(c["success_rate"], c["est_execution_time"])
            scored.append((score, c["name"]))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
