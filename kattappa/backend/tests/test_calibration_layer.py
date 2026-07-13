import uuid
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.observability.calibration_cal import (
    calculate_brier_score,
    calculate_ece,
    compile_calibration_report,
)


def test_calibration_math():
    # Test Brier score calculation
    # Perfect score
    assert calculate_brier_score([1.0, 0.0], [1, 0]) == 0.0
    # Complete miscalibration
    assert calculate_brier_score([1.0, 0.0], [0, 1]) == 1.0
    # Average calibration
    assert calculate_brier_score([0.9, 0.1], [1, 0]) == 0.01

    # Test ECE calculation
    # ECE with 5 bins
    preds = [0.9, 0.9, 0.1, 0.1]
    outs = [1, 1, 0, 0]
    # Bin 0 (0.0-0.2): conf=0.1, acc=0.0 -> diff=0.1. Size=2. ECE contribution = 2/4 * 0.1 = 0.05
    # Bin 4 (0.8-1.0): conf=0.9, acc=1.0 -> diff=0.1. Size=2. ECE contribution = 2/4 * 0.1 = 0.05
    # Total ECE = 0.10
    assert calculate_ece(preds, outs, num_bins=5) == 0.10


def test_sqlite_outcome_persistence():
    decision_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    
    # Record outcome
    KERNEL.ledger.record_outcome(
        calibration_id=str(uuid.uuid4()),
        decision_id=decision_id,
        trace_id=trace_id,
        stage="planner",
        predicted_confidence=0.95,
        actual_result=1,
        error_message=None
    )
    
    # Query database
    cals = KERNEL.ledger.get_calibrations("planner")
    assert len(cals) >= 1
    assert any(c["decision_id"] == decision_id for c in cals)


def test_calibration_endpoints():
    client = TestClient(app)
    
    dec_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    
    # 1. Post outcome
    response = client.post(
        "/api/v1/telemetry/outcome",
        json={
            "decision_id": dec_id,
            "trace_id": trace_id,
            "stage": "tool",
            "predicted_confidence": 0.85,
            "actual_result": 1,
            "error_message": None,
        }
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # 2. Query calibration report
    response = client.get("/api/v1/telemetry/calibration/report")
    assert response.status_code == 200
    report = response.json()
    assert report["total_records"] >= 1
    assert "brier_score" in report
    assert "ece" in report
    assert "histogram" in report
