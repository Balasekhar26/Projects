from backend.core.curriculum.performance_analyzer import PerformanceAnalyzer
from backend.core.curriculum.curriculum_planner import CurriculumPlanner
from backend.core.curriculum.learning_scheduler import LearningScheduler

class CurriculumLearningEngine:
    def __init__(self):
        self.analyzer = PerformanceAnalyzer()
        self.planner = CurriculumPlanner()
        self.scheduler = LearningScheduler()

    def trigger_curriculum_cycles(self, system_telemetry: dict, failure_threshold: float = 0.15) -> list[dict]:
        """Runs weakness checks and returns learning exercises if system parameters are idle."""
        if not self.scheduler.is_system_idle(system_telemetry):
            return []
            
        weak_skills = self.analyzer.identify_weak_skills(failure_threshold)
        return self.planner.generate_curriculum(weak_skills)
