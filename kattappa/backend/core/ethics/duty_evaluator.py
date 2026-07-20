class DutyEvaluator:
    AUTHORIZED_DOMAINS = {"software_development", "research", "data_analysis", "system_maintenance"}

    @classmethod
    def evaluate_duty(cls, task_domain: str) -> float:
        """Scores a task domain against user-authorized execution duty profiles."""
        domain = task_domain.lower().strip()
        if domain in cls.AUTHORIZED_DOMAINS:
            return 0.90
            
        return 0.10
