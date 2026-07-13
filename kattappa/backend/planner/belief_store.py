import time
from typing import Any, Dict, List, Optional, Tuple

class BeliefEntry:
    """Represents a single belief entry with uncertainty, provenance, and decay parameters."""

    def __init__(
        self,
        value: Any,
        confidence: float,
        source: str,
        decay_rate: float = 0.05,
        provenance: str = "observation"
    ) -> None:
        self.value = value
        self.confidence = confidence
        self.source = source
        self.decay_rate = decay_rate
        self.provenance = provenance
        self.timestamp = time.time()
        self.evidence_history: List[Tuple[float, Any, str]] = [(self.timestamp, value, source)]

    def add_evidence(self, value: Any, source: str, source_credibility: float) -> None:
        """Accumulates evidence to adjust value and confidence scores."""
        now = time.time()
        self.evidence_history.append((now, value, source))
        
        # Calculate new value consensus and update confidence based on credibility
        if value == self.value:
            # Reaffirming evidence increases confidence asymptotically
            self.confidence = min(1.0, self.confidence + (1.0 - self.confidence) * source_credibility)
        else:
            # Contradictory evidence creates a conflict, decaying current confidence
            self.confidence = max(0.0, self.confidence - source_credibility)
            if self.confidence < 0.2:
                # Flip value if contradiction confidence drops low enough
                self.value = value
                self.confidence = source_credibility

        self.timestamp = now

    def decay_confidence(self, time_elapsed: float) -> None:
        """Decays the belief confidence over time to reflect volatile conditions."""
        decay_factor = self.decay_rate * time_elapsed
        self.confidence = max(0.0, self.confidence - decay_factor)


class BeliefStore:
    """Manages beliefs and checks confidence thresholds for task operations with local disk persistence."""

    def __init__(self) -> None:
        import json
        from pathlib import Path
        self.filepath = Path("backend/data/belief_store.json")
        self.beliefs: Dict[str, BeliefEntry] = {}
        self.load()

    def load(self) -> None:
        """Loads beliefs state from local file database."""
        import json
        if self.filepath.exists():
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                for key, val in data.items():
                    entry = BeliefEntry(
                        value=val["value"],
                        confidence=val["confidence"],
                        source=val["source"],
                        decay_rate=val.get("decay_rate", 0.05),
                        provenance=val.get("provenance", "observation")
                    )
                    entry.timestamp = val.get("timestamp", time.time())
                    self.beliefs[key] = entry
            except Exception:
                pass

    def save(self) -> None:
        """Saves current beliefs state to local file database."""
        import json
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for key, entry in self.beliefs.items():
                data[key] = {
                    "value": entry.value,
                    "confidence": entry.confidence,
                    "source": entry.source,
                    "decay_rate": entry.decay_rate,
                    "provenance": entry.provenance,
                    "timestamp": entry.timestamp
                }
            with open(self.filepath, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def set_belief(
        self,
        key: str,
        value: Any,
        confidence: float,
        source: str,
        decay_rate: float = 0.01,
        provenance: str = "observation"
    ) -> None:
        """Sets a belief value or updates it if it exists, persisting to disk."""
        if key in self.beliefs:
            self.beliefs[key].add_evidence(value, source, confidence)
        else:
            self.beliefs[key] = BeliefEntry(value, confidence, source, decay_rate, provenance)
        self.save()

    def get_belief(self, key: str) -> Optional[Tuple[Any, float]]:
        """Gets value and confidence after applying temporal decay checks."""
        entry = self.beliefs.get(key)
        if not entry:
            return None
        
        # Apply decay based on elapsed time since last update
        now = time.time()
        elapsed = now - entry.timestamp
        if elapsed > 0:
            entry.decay_confidence(elapsed)
            entry.timestamp = now
            self.save()

        return entry.value, entry.confidence

    def check_threshold(self, key: str, threshold: float) -> Tuple[bool, Optional[Any]]:
        """Checks if confidence meets action threshold. Returns (is_valid, value)."""
        res = self.get_belief(key)
        if not res:
            return False, None
        val, conf = res
        if conf >= threshold:
            return True, val
        return False, val
