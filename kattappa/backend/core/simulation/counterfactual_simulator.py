from backend.core.simulation.future_state_predictor import FutureStatePredictor

class CounterfactualSimulator:
    @classmethod
    def simulate_path(cls, initial_state: dict, commands: list[str]) -> dict:
        """Evaluates hypothetical commands pathways sequentially and returns final projected state."""
        state = dict(initial_state)
        for cmd in commands:
            state = FutureStatePredictor.predict_state_change(state, cmd)
        return state
