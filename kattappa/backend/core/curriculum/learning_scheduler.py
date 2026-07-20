class LearningScheduler:
    @classmethod
    def is_system_idle(cls, system_telemetry: dict) -> bool:
        """Verifies if system CPU and RAM usage rates permit background learning cycles."""
        cpu = system_telemetry.get("cpu_percent", 0.0)
        ram = system_telemetry.get("memory_percent", 0.0)
        
        # System is idle if CPU < 20% and memory < 60%
        return cpu < 20.0 and ram < 60.0
