import pytest
from backend.core.simulation.future_state_predictor import FutureStatePredictor
from backend.core.simulation.risk_estimator import RiskEstimator
from backend.core.simulation.counterfactual_simulator import CounterfactualSimulator
from backend.core.simulation.predictive_simulation_engine import PredictiveSimulationEngine

def test_future_state_predictor_create() -> None:
    state = {"files": ["readme.md"]}
    predicted = FutureStatePredictor.predict_state_change(state, "create notes.txt")
    assert "notes.txt" in predicted["files"]
    assert "readme.md" in predicted["files"]

def test_future_state_predictor_delete() -> None:
    state = {"files": ["readme.md", "temp.log"]}
    predicted = FutureStatePredictor.predict_state_change(state, "delete temp.log")
    assert "temp.log" not in predicted["files"]
    assert "readme.md" in predicted["files"]

def test_risk_estimator_flags_destructive() -> None:
    assert RiskEstimator.estimate_risk("rm -rf /project") >= 0.90
    assert RiskEstimator.estimate_risk("delete all_data") >= 0.90
    assert RiskEstimator.estimate_risk("list files") < 0.10

def test_counterfactual_path_simulation() -> None:
    initial = {"files": ["a.py"]}
    commands = ["create b.py", "create c.py", "delete a.py"]
    final = CounterfactualSimulator.simulate_path(initial, commands)
    assert "a.py" not in final["files"]
    assert "b.py" in final["files"]
    assert "c.py" in final["files"]

def test_engine_orchestration() -> None:
    engine = PredictiveSimulationEngine()
    
    # Risk check
    assert engine.get_action_risk("rm database.db") >= 0.90
    assert engine.get_action_risk("read config.yaml") < 0.10
    
    # Forecast
    state = {"files": ["main.py"]}
    outcome = engine.forecast_outcome(state, "create utils.py")
    assert "utils.py" in outcome["files"]
    
    # Hypothetical sequence
    final = engine.evaluate_hypothetical_sequence(
        {"files": ["old.log"]},
        ["delete old.log", "create new.log"]
    )
    assert "old.log" not in final["files"]
    assert "new.log" in final["files"]
