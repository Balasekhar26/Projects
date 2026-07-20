from datetime import datetime

class EventSegmenter:
    @classmethod
    def segment_events(cls, episodes: list[dict], segment_threshold_sec: float = 300.0) -> list[list[dict]]:
        """Groups chronological episodes list into session epochs if elapsed time exceeds threshold."""
        if not episodes:
            return []
            
        # Ensure chronological order (oldest first)
        sorted_episodes = sorted(episodes, key=lambda e: e["created_at"])
        
        segments = []
        current_segment = [sorted_episodes[0]]
        
        for ep in sorted_episodes[1:]:
            last_time = datetime.fromisoformat(current_segment[-1]["created_at"])
            curr_time = datetime.fromisoformat(ep["created_at"])
            
            delta = (curr_time - last_time).total_seconds()
            if delta > segment_threshold_sec:
                segments.append(current_segment)
                current_segment = [ep]
            else:
                current_segment.append(ep)
                
        segments.append(current_segment)
        return segments
