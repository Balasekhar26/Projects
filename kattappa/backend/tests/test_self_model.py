import pytest
import os
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.self_model.capability_registry import CapabilityRegistry
from backend.core.self_model.confidence_engine import ConfidenceEngine
from backend.core.self_model.uncertainty_estimator import UncertaintyEstimator
from backend.core.self_model.self_model_engine import SelfModelEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_self_model_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_capability_registry_checks() -> None:
    registry = CapabilityRegistry()
    assert registry.is_command_supported("git commit -m 'save'")
    assert not registry.is_command_supported("rm -rf /")

def test_confidence_calculations(test_db_setup) -> None:
    # Baseline
    assert ConfidenceEngine.calculate_confidence("g_new") == 0.80
    
    # Register outcome history runs
    from backend.core.agent.reflector import Reflector
    Reflector.reflect_on_outcome("g_calib", success=True, duration=1.0)
    Reflector.reflect_on_outcome("g_calib", success=False, duration=1.0)
    
    # 1 success out of 2 total = 0.50
    assert ConfidenceEngine.calculate_confidence("g_calib") == 0.50

def test_uncertainty_thresholds() -> None:
    # High confidence values -> low uncertainty (1.0 - 0.9 * 0.9 = 0.19)
    unc_low = UncertaintyEstimator.estimate_uncertainty(0.9, 0.9)
    assert unc_low < 0.20
    assert not UncertaintyEstimator.requires_human_approval(unc_low)
    
    # Low confidence values -> high uncertainty (1.0 - 0.7 * 0.8 = 0.44)
    unc_high = UncertaintyEstimator.estimate_uncertainty(0.7, 0.8)
    assert unc_high >= 0.30
    assert UncertaintyEstimator.requires_human_approval(unc_high)

def test_self_model_engine_coordination(test_db_setup) -> None:
    engine = SelfModelEngine()
    
    # Supported command, high layout confidence
    res = engine.evaluate_task_safety_and_confidence("t1", "git pull", 0.95, 0.95)
    assert res["supported"]
    assert not res["requires_human_approval"]
    
    # Unsupported command, high layout confidence
    res_bad = engine.evaluate_task_safety_and_confidence("t2", "rm -rf root", 0.95, 0.95)
    assert not res_bad["supported"]
    assert res_bad["requires_human_approval"] # Should trigger gate if unsupported
