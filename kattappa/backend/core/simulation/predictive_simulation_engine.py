from backend.core.simulation.future_state_predictor import FutureStatePredictor
from backend.core.simulation.risk_estimator import RiskEstimator
from backend.core.simulation.counterfactual_simulator import CounterfactualSimulator

class PredictiveSimulationEngine:
    def __init__(self):
        self.predictor = FutureStatePredictor()
        self.risk_estimator = RiskEstimator()
        self.simulator = CounterfactualSimulator()

    def get_action_risk(self, command: str) -> float:
        """Retrieves estimated risk score for a command."""
        return self.risk_estimator.estimate_risk(command)

    def forecast_outcome(self, current_state: dict, command: str) -> dict:
        """Projects outcome state change after running a command."""
        return self.predictor.predict_state_change(current_state, command)

    def evaluate_hypothetical_sequence(self, initial_state: dict, commands: list[str]) -> dict:
        """Simulates path execution output state."""
        return self.simulator.simulate_path(initial_state, commands)
