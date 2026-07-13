import os
import zipfile
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.ledger.telemetry.metrics_collector import MetricsCollector
from backend.core.observability.diagnostics import export_diagnostics_bundle


def test_sqlite_metrics_persistence():
    # Verify that recording a metric adds it to the SQLite store
    collector = MetricsCollector()
    
    # Record a test metric
    collector.record("cpu_usage", 82.5, {"reason": "test"})
    
    # Retrieve the metric values
    vals = KERNEL.ledger.get_metric_values("cpu_usage")
    assert len(vals) >= 1
    # Check that the recorded value matches
    assert any(v == 82.5 for _, v in vals)


def test_diagnostics_bundle_generation():
    # Export the diagnostics bundle
    zip_path = export_diagnostics_bundle()
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
    
    # Verify contents of zip file
    with zipfile.ZipFile(zip_path, "r") as z:
        files = z.namelist()
        assert "system_info.json" in files
        assert "metrics_history.json" in files
        assert "agent_log_tail.txt" in files
        
    # Cleanup file
    os.remove(zip_path)


def test_telemetry_endpoints():
    client = TestClient(app)
    
    # Test report endpoint
    response = client.get("/api/v1/telemetry/report")
    assert response.status_code == 200
    assert "cpu_usage" in response.json()

    # Test stats endpoint
    response = client.get("/api/v1/telemetry/stats")
    assert response.status_code == 200
    assert "tokens" in response.json()

    # Test timeline endpoint
    response = client.get("/api/v1/telemetry/timeline")
    assert response.status_code == 200

    # Test diagnostics file response endpoint
    response = client.get("/api/v1/telemetry/diagnostics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
