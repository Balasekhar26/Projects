from backend.core.world_model.state_predictor import StatePredictor
from backend.core.world_model.outcome_simulator import OutcomeSimulator
from backend.core.world_model.risk_estimator import RiskEstimator
from backend.core.world_model.counterfactual_engine import CounterfactualEngine

class WorldModelEngine:
    def __init__(self):
        self.predictor = StatePredictor()
        self.simulator = OutcomeSimulator()
        self.risk_estimator = RiskEstimator()
        self.counterfactual = CounterfactualEngine()

    def evaluate_action_sequence(self, current_state: str, steps: list[dict]) -> dict:
        """Evaluates dynamic risk variables, success probabilities, and predicted state endpoints."""
        # 1. Success rate simulation
        success_prob = self.simulator.simulate_plan_success(steps)
        
        # 2. Risk estimation (max risk across steps)
        max_risk = 0.0
        predicted_state = current_state
        
        for step in steps:
            cmd = step.get("cmd", "")
            step_risk = self.risk_estimator.estimate_action_risk(cmd)
            max_risk = max(max_risk, step_risk)
            predicted_state = self.predictor.predict_future_state(predicted_state, cmd)
            
        return {
            "success_probability": success_prob,
            "max_risk": max_risk,
            "is_high_risk": max_risk >= 0.40,
            "predicted_final_state": predicted_state
        }
