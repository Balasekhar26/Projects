import pytest
from backend.core.world_model.state_predictor import StatePredictor
from backend.core.world_model.outcome_simulator import OutcomeSimulator
from backend.core.world_model.risk_estimator import RiskEstimator
from backend.core.world_model.counterfactual_engine import CounterfactualEngine
from backend.core.world_model.world_model_engine import WorldModelEngine

def test_state_predictor_transitions() -> None:
    predictor = StatePredictor()
    assert predictor.predict_future_state("INITIAL", "click save button") == "FILE_SAVED"
    assert predictor.predict_future_state("INITIAL", "rm -rf folder") == "FILE_DELETED"
    assert predictor.predict_future_state("NOTEPAD", "click save") == "FILE_SAVED"

def test_outcome_simulator_joint_prob() -> None:
    simulator = OutcomeSimulator()
    # Empty plan
    assert simulator.simulate_plan_success([]) == 1.0
    
    # 2 steps at 0.90 step probability
    prob = simulator.simulate_plan_success([{"cmd": "click"}, {"cmd": "type"}], single_step_prob=0.90)
    assert pytest.approx(prob) == 0.81

def test_risk_estimator_ratings() -> None:
    estimator = RiskEstimator()
    risk_low = estimator.estimate_action_risk("click button")
    risk_high = estimator.estimate_action_risk("rm -rf target")
    
    assert risk_low < 0.10
    assert risk_high >= 0.40  # 0.5 * 0.9 = 0.45

def test_counterfactual_divergences() -> None:
    engine = CounterfactualEngine()
    res = engine.evaluate_counterfactual("INITIAL", "click save button", "click cancel")
    
    assert res["diverges"]
    assert res["chosen_path"]["predicted_state"] == "FILE_SAVED"
    assert res["alternative_path"]["predicted_state"] == "CLICKED_INITIAL"

def test_world_model_engine_aggregation() -> None:
    engine = WorldModelEngine()
    
    steps = [
        {"cmd": "click button"},
        {"cmd": "rm -rf junk"}
    ]
    res = engine.evaluate_action_sequence("INITIAL", steps)
    
    # Success probability should be 0.95^2 = 0.9025
    assert pytest.approx(res["success_probability"]) == 0.9025
    # Max risk is high due to rm command
    assert res["is_high_risk"]
    assert res["predicted_final_state"] == "FILE_DELETED"
