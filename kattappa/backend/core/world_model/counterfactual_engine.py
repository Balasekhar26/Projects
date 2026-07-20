from backend.core.world_model.state_predictor import StatePredictor

class CounterfactualEngine:
    def __init__(self):
        self.predictor = StatePredictor()

    def evaluate_counterfactual(self, current_state: str, action: str, alternative_action: str) -> dict:
        """Compares predicted future state transitions between the selected action and an alternative candidate."""
        state_act = self.predictor.predict_future_state(current_state, action)
        state_alt = self.predictor.predict_future_state(current_state, alternative_action)
        
        return {
            "chosen_path": {
                "action": action,
                "predicted_state": state_act
            },
            "alternative_path": {
                "action": alternative_action,
                "predicted_state": state_alt
            },
            "diverges": state_act != state_alt
        }
