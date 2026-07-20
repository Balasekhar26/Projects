class GracefulDegradation:
    @classmethod
    def get_active_features(cls, cpu_percent: float) -> list[str]:
        """Limits active system feature list when resource usage exceeds threshold parameters."""
        if cpu_percent >= 80.0:
            return ["basic_text_execution"]
            
        return ["basic_text_execution", "background_learning", "voice_streaming"]
