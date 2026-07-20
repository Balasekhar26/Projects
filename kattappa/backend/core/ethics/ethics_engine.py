from backend.core.ethics.duty_evaluator import DutyEvaluator
from backend.core.ethics.harm_predictor import HarmPredictor
from backend.core.ethics.alignment_validator import AlignmentValidator

class EthicsEngine:
    def __init__(self):
        self.duty_evaluator = DutyEvaluator()
        self.harm_predictor = HarmPredictor()
        self.alignment_validator = AlignmentValidator()

    def audit_task(self, command: str, task_domain: str) -> dict:
        """Runs ethical evaluation on a command and domain returns safety audit report."""
        duty_score = self.duty_evaluator.evaluate_duty(task_domain)
        harm_score = self.harm_predictor.predict_harm(command)
        aligned = self.alignment_validator.is_aligned(harm_score, duty_score)
        
        return {
            "duty_score": duty_score,
            "harm_score": harm_score,
            "is_aligned": aligned
        }
