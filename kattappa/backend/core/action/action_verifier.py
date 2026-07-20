class ActionVerifier:
    @classmethod
    def verify_state_change(cls, pre_snapshot: bytes | None, post_snapshot: bytes | None) -> bool:
        """Compares screen state screenshots and returns True if a layout state change has occurred."""
        if pre_snapshot is None or post_snapshot is None:
            return False
            
        # Simply evaluates canvas changes
        # In production, this computes Structural Similarity Index (SSIM) bounds
        return pre_snapshot != post_snapshot
