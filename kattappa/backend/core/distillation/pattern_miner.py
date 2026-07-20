from collections import Counter

class PatternMiner:
    @classmethod
    def mine_repeated_sequences(cls, action_sequences: list[list[str]], pattern_length: int = 2, min_reps: int = 2) -> list[tuple[tuple[str, ...], int]]:
        """Scans historical lists of action command steps sequences and returns patterns that recur at least min_reps times."""
        patterns = []
        for seq in action_sequences:
            if len(seq) < pattern_length:
                continue
                
            # Sliding window of size pattern_length
            for i in range(len(seq) - pattern_length + 1):
                sub = tuple(seq[i:i+pattern_length])
                patterns.append(sub)
                
        counts = Counter(patterns)
        return [(pat, count) for pat, count in counts.items() if count >= min_reps]
