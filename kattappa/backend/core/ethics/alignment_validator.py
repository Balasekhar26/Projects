class AlignmentValidator:
    @classmethod
    def is_aligned(cls, harm_score: float, duty_score: float) -> bool:
        """Determines if a task aligns with core system guidelines based on safety vs authorization."""
        # A task is unaligned if harm score is high and duty/authorization score is low
        if harm_score >= 0.80 and duty_score < 0.80:
            return False
            
        return True
