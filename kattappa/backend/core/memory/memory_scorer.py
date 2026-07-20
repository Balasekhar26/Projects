from __future__ import annotations
import math
from datetime import datetime

class MemoryScorer:
    @classmethod
    def calculate_score(cls, memory: dict) -> float:
        """Computes relevance score using importance, confidence decay, and access boosts."""
        importance = memory.get("importance") or 0.5
        confidence = memory.get("confidence") or 1.0
        access_count = memory.get("access_count") or 0
        
        boost = 1.0 + math.log(access_count + 1)
        
        # Compute temporal confidence decay: e^(-0.01 * days)
        created_at_str = memory.get("created_at")
        decayed_confidence = confidence
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                delta = datetime.now() - created_at
                days = delta.total_seconds() / 86400.0
                decayed_confidence = confidence * math.exp(-0.01 * days)
            except Exception:
                pass
                
        return importance * decayed_confidence * boost
