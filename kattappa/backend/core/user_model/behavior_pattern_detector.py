from collections import Counter

class BehaviorPatternDetector:
    def __init__(self):
        self._history: list[str] = []

    def record_action(self, action: str) -> None:
        """Appends an action to the interaction history."""
        self._history.append(action)

    def detect_patterns(self, window_size: int = 2, min_occurrences: int = 2) -> list[tuple[tuple[str, ...], int]]:
        """Scans history with a sliding window and returns recurring sequences."""
        if len(self._history) < window_size:
            return []

        patterns: list[tuple[str, ...]] = []
        for i in range(len(self._history) - window_size + 1):
            patterns.append(tuple(self._history[i:i + window_size]))

        counts = Counter(patterns)
        return [
            (pat, count)
            for pat, count in counts.most_common()
            if count >= min_occurrences
        ]
