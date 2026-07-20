import pytest
from backend.core.ethics.duty_evaluator import DutyEvaluator
from backend.core.ethics.harm_predictor import HarmPredictor
from backend.core.ethics.alignment_validator import AlignmentValidator
from backend.core.ethics.ethics_engine import EthicsEngine

def test_duty_evaluator_scoring() -> None:
    # Authorized domain
    assert DutyEvaluator.evaluate_duty("software_development") == 0.90
    # Unauthorized domain
    assert DutyEvaluator.evaluate_duty("unauthorized_gaming") == 0.10

def test_harm_predictor_patterns() -> None:
    # Harmful pattern
    assert HarmPredictor.predict_harm("rm -rf /sys/config") == 0.85
    # Safe command
    assert HarmPredictor.predict_harm("read configurations") == 0.05

def test_alignment_validator_bounds() -> None:
    # Case 1: High harm, low duty -> Unaligned
    assert not AlignmentValidator.is_aligned(harm_score=0.85, duty_score=0.10)
    
    # Case 2: High harm, high duty -> Aligned (authorized critical operations)
    assert AlignmentValidator.is_aligned(harm_score=0.85, duty_score=0.90)
    
    # Case 3: Low harm, low duty -> Aligned
    assert AlignmentValidator.is_aligned(harm_score=0.05, duty_score=0.10)

def test_ethics_engine_coordination() -> None:
    engine = EthicsEngine()
    
    # 1. Test unaligned case
    res1 = engine.audit_task("rm -rf /sys", "unauthorized_gaming")
    assert res1["duty_score"] == 0.10
    assert res1["harm_score"] == 0.85
    assert res1["is_aligned"] is False
    
    # 2. Test aligned critical case
    res2 = engine.audit_task("rm -rf /sys", "system_maintenance")
    assert res2["duty_score"] == 0.90
    assert res2["harm_score"] == 0.85
    assert res2["is_aligned"] is True
