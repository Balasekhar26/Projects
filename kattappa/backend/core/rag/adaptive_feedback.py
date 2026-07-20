import json
import uuid
from datetime import datetime
from backend.core.memory.memory_store import MemoryStore

class AdaptiveFeedback:
    @classmethod
    def record_feedback(
        cls,
        query: str,
        retrieved_chunk_ids: list[str],
        selected_chunk_ids: list[str],
        answer_quality: float,
        user_feedback: int
    ) -> None:
        """Records retrieval quality metrics and user selections to target subsequent query rankings."""
        feedback_id = str(uuid.uuid4())
        MemoryStore.add_retrieval_feedback(
            feedback_id=feedback_id,
            query=query,
            retrieved_chunk_ids=retrieved_chunk_ids,
            selected_chunk_ids=selected_chunk_ids,
            answer_quality=answer_quality,
            user_feedback=user_feedback
        )

    @classmethod
    def get_chunk_penalties(cls) -> dict[str, float]:
        """Calculates chunk penalties using time-decayed metrics for negative feedback events."""
        feedbacks = MemoryStore.get_all_retrieval_feedback()
        # Sort by timestamp descending so index 0 is the most recent feedback
        feedbacks.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        penalties = {}
        for index, fb in enumerate(feedbacks):
            user_feedback = fb.get("user_feedback", 0)
            quality = fb.get("answer_quality", 1.0)
            
            # Apply penalty decay factor: recent negative feedback has a higher impact
            decay_factor = 0.95 ** index
            
            # Penalty triggers on negative feedback (-1) or low quality (< 0.5)
            if user_feedback == -1 or quality < 0.5:
                try:
                    retrieved = json.loads(fb["retrieved_chunk_ids"])
                    selected = json.loads(fb["selected_chunk_ids"])
                except Exception:
                    continue
                    
                # Penalize chunks that were retrieved but not selected by the user/agent
                for chunk_id in retrieved:
                    if chunk_id not in selected:
                        base_penalty = 0.1 * decay_factor
                        penalties[chunk_id] = penalties.get(chunk_id, 0.0) + base_penalty
                        
        return penalties
