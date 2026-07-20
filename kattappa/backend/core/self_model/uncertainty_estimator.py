class UncertaintyEstimator:
    @classmethod
    def estimate_uncertainty(cls, vision_confidence: float, ocr_confidence: float) -> float:
        """Computes system layout layout prediction uncertainty index."""
        # Uncertainty is the inverse of product of confidence values
        return 1.0 - (vision_confidence * ocr_confidence)

    @classmethod
    def requires_human_approval(cls, uncertainty_score: float) -> bool:
        """Determines if the uncertainty index exceeds threshold boundaries (e.g. >= 0.30) requiring review gates."""
        return uncertainty_score >= 0.30
