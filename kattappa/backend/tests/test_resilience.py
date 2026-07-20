import pytest
from backend.core.resilience.retry_manager import RetryManager
from backend.core.resilience.rollback_engine import RollbackEngine
from backend.core.resilience.graceful_degradation import GracefulDegradation
from backend.core.resilience.resilience_engine import ResilienceEngine

def test_retry_manager_success_after_failure() -> None:
    calls = []
    
    def mock_action():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("Intermittent failure")
        return "success"
        
    res = RetryManager.execute_with_retry(mock_action, max_attempts=3, initial_delay_sec=0.01)
    assert res == "success"
    assert len(calls) == 2

def test_retry_manager_raises_after_max_attempts() -> None:
    def mock_action():
        raise ValueError("Constant failure")
        
    with pytest.raises(ValueError, match="Constant failure"):
        RetryManager.execute_with_retry(mock_action, max_attempts=2, initial_delay_sec=0.01)

def test_rollback_engine_checkpoint() -> None:
    initial = {"files": ["main.py"], "status": "stable"}
    corrupted = {"files": ["main.py", "corrupted.tmp"], "status": "error"}
    
    restored = RollbackEngine.rollback_state(initial)
    assert restored["status"] == "stable"
    assert "corrupted.tmp" not in restored["files"]

def test_graceful_degradation_active_features() -> None:
    # Under high load (>= 80%)
    features_busy = GracefulDegradation.get_active_features(85.0)
    assert features_busy == ["basic_text_execution"]
    
    # Under low load (< 80%)
    features_idle = GracefulDegradation.get_active_features(15.0)
    assert "background_learning" in features_idle
    assert "voice_streaming" in features_idle

def test_resilience_engine_workflow() -> None:
    engine = ResilienceEngine()
    
    # Verify retry run
    calls = []
    def act():
        calls.append(1)
        return "ok"
    assert engine.run_safe_retry(act) == "ok"
    
    # Verify rollback run
    checkpoint = {"env": "test"}
    assert engine.trigger_rollback(checkpoint) == {"env": "test"}
    
    # Verify degradation levels
    assert engine.determine_system_features(90.0) == ["basic_text_execution"]
