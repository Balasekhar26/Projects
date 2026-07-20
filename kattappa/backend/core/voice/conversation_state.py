class ConversationStateManager:
    def __init__(self):
        self.active_speaker_state = "IDLE"  # IDLE, LISTENING, SPEAKING
        self.turn_ownership = "USER"        # USER, ASSISTANT
        self.partial_transcript = ""
        self.is_interrupted = False
        self.response_queue = []

    def reset(self) -> None:
        """Resets the dialogue session states."""
        self.active_speaker_state = "IDLE"
        self.turn_ownership = "USER"
        self.partial_transcript = ""
        self.is_interrupted = False
        self.response_queue.clear()

    def merge_transcripts(self, current: str, new_segment: str) -> str:
        """Cleans and merges overlapping partial audio transcript windows."""
        current = current.strip()
        new_segment = new_segment.strip()
        if not current:
            return new_segment
        if not new_segment:
            return current
            
        current_words = current.split()
        new_words = new_segment.split()
        
        # Check for overlap from longest to shortest suffix
        max_overlap = min(len(current_words), len(new_words))
        overlap_size = 0
        
        for i in range(1, max_overlap + 1):
            suffix = current_words[-i:]
            prefix = new_words[:i]
            if suffix == prefix:
                overlap_size = i
                
        if overlap_size > 0:
            merged_words = current_words + new_words[overlap_size:]
            return " ".join(merged_words)
        else:
            # Fallback to simple concatenation if no overlap matches
            return current + " " + new_segment
