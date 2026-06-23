import os
import shutil
import tempfile
import time
import json
import re
import pytest
from pathlib import Path

from backend.agents.monitoring import MonitoringAgent, monitoring_node
from backend.core.resource_governor import ResourceGovernor
from backend.core.capability_registry import CapabilityRegistry
from backend.core.memory_service import MemoryService
from backend.core.human_memory import HumanMemory


@pytest.fixture
def clean_monitor_env(monkeypatch):
    """Sets a temporary folder for memory/governor data and resets systems."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_monitor_test_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    HumanMemory.reset()
    ResourceGovernor.reset()
    
    # Ensure local cache in MonitoringAgent is cleared
    MonitoringAgent._last_sample = None
    MonitoringAgent._last_sample_time = 0.0

    # Reset schema ensured flags for clean DB setup
    from backend.core.memory_governance import MemoryGovernance
    from backend.core.episodic_memory import EpisodicMemory
    from backend.core.semantic_memory import SemanticMemory
    from backend.core.relationship_memory import RelationshipMemory
    from backend.core.strategic_memory import StrategicMemory
    from backend.core.reflection_memory import ReflectionMemory
    from backend.core.procedural_memory import ProceduralMemory
    from backend.core.working_memory import WorkingMemory

    MemoryGovernance._schema_ensured = False
    EpisodicMemory._schema_ensured = False
    SemanticMemory._schema_ensured = False
    RelationshipMemory._schema_ensured = False
    StrategicMemory._schema_ensured = False
    ReflectionMemory._schema_ensured = False
    ProceduralMemory._schema_ensured = False
    WorkingMemory._schema_ensured = False
    
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_metrics_collection_success(clean_monitor_env):
    res = MonitoringAgent.collect_metrics("monitoring")
    assert res["success"] is True
    metrics = res["metrics"]
    assert "cpu_percent" in metrics
    assert "ram_percent" in metrics
    assert "gpu_usage" in metrics
    assert "disk_percent" in metrics
    assert "network_rx_bytes" in metrics
    assert "network_tx_bytes" in metrics


def test_health_analysis_thresholds(clean_monitor_env):
    # Normal metrics
    normal_metrics = {
        "cpu_percent": 10.0,
        "ram_percent": 50.0,
        "cpu_temp": 55.0,
        "gpu_temp": 60.0,
        "disk_percent": 40.0
    }
    h_normal = MonitoringAgent.analyze_health(normal_metrics)
    assert h_normal["status"] == "GOOD"
    assert h_normal["health_score"] == 100
    assert len(h_normal["alerts"]) == 0

    # Warning metrics (CPU warning)
    warning_metrics = {
        "cpu_percent": 75.0,
        "ram_percent": 50.0,
        "cpu_temp": 55.0,
        "disk_percent": 40.0
    }
    h_warning = MonitoringAgent.analyze_health(warning_metrics)
    assert h_warning["status"] == "WARNING"
    assert h_warning["health_score"] == 85
    assert len(h_warning["alerts"]) == 1

    # Critical metrics (RAM critical)
    critical_metrics = {
        "cpu_percent": 10.0,
        "ram_percent": 96.0,
        "cpu_temp": 55.0,
        "disk_percent": 40.0
    }
    h_critical = MonitoringAgent.analyze_health(critical_metrics)
    assert h_critical["status"] == "CRITICAL"
    assert h_critical["health_score"] == 65
    assert len(h_critical["alerts"]) == 1


def test_recommendations(clean_monitor_env):
    alerts = [
        {"metric": "CPU", "level": "WARNING"},
        {"metric": "RAM", "level": "CRITICAL"},
        {"metric": "Disk", "level": "CRITICAL"},
        {"metric": "GPU Temp", "level": "WARNING"}
    ]
    recs = MonitoringAgent.generate_recommendations(alerts)
    assert "Close heavy processes" in recs
    assert "Restart memory-intensive services" in recs
    assert "Archive logs" in recs
    assert "Increase cooling" in recs


def test_security_readonly_capabilities(clean_monitor_env, monkeypatch):
    # Deny CPU monitoring capability
    monkeypatch.setattr(
        CapabilityRegistry,
        "is_capability_allowed",
        lambda agent, cap: cap != "CAP_MONITOR_CPU"
    )

    res = MonitoringAgent.collect_metrics("monitoring")
    assert res["success"] is True
    # CPU should default to 0.0 because capability is denied
    assert res["metrics"]["cpu_percent"] == 0.0


def test_security_no_execution_functions(clean_monitor_env):
    # Programmatic audit of monitoring.py contents to ensure no mutating shell or file deletions
    from backend.core.config import load_config
    monitoring_path = load_config().backend_root / "agents" / "monitoring.py"
    content = monitoring_path.read_text(encoding="utf-8")
    
    # Ensure no process execution keywords or deletes exist in our agent methods
    forbidden = ["kill_process", "restart_service", "delete_files", "subprocess.run"]
    for f in forbidden:
        assert f not in content


def test_security_no_secrets_in_reports(clean_monitor_env):
    metrics = {"cpu_percent": 10.0, "ram_percent": 50.0}
    health = {"status": "GOOD", "health_score": 100, "alerts": []}
    
    # Recommendations with embedded credentials
    recs = ["Close heavy processes for api_key='sk-12345abcdef' database"]
    short_rep = MonitoringAgent.generate_short_report(metrics, health, recs)
    detailed_rep = MonitoringAgent.generate_detailed_report(metrics, health, recs, [metrics])
    
    assert "sk-12345abcdef" not in short_rep
    assert "[REDACTED]" in short_rep
    assert "sk-12345abcdef" not in detailed_rep
    assert "[REDACTED]" in detailed_rep


def test_resource_governor_rate_limiting(clean_monitor_env, monkeypatch):
    res1 = MonitoringAgent.collect_metrics("monitoring")
    assert res1["success"] is True
    assert res1.get("cached") is not True

    # Call immediately after (within 1 second)
    res2 = MonitoringAgent.collect_metrics("monitoring")
    assert res2["success"] is True
    assert res2.get("cached") is True


def test_resource_governor_history_limits(clean_monitor_env, monkeypatch):
    # Add dummy samples to stats to verify it pops oldest
    stats = MonitoringAgent.load_stats()
    stats["samples_history"] = [{"cpu_percent": 10.0}] * 3600
    MonitoringAgent.save_stats(stats)
    
    # Collect new metrics
    res = MonitoringAgent.collect_metrics("monitoring")
    assert res["success"] is True
    
    stats_after = MonitoringAgent.load_stats()
    # History must be clamped to 3600
    assert len(stats_after["samples_history"]) == 3600


def test_short_and_detailed_reports(clean_monitor_env):
    metrics = {
        "cpu_percent": 45.0,
        "ram_percent": 60.0,
        "gpu_usage": 20.0,
        "disk_percent": 65.0,
        "ram_used_mb": 4096.0,
        "ram_available_mb": 4096.0,
        "network_rx_bytes": 1000,
        "network_tx_bytes": 500,
        "network_latency_ms": 10.0
    }
    health = {"status": "GOOD", "health_score": 100, "alerts": []}
    recs = []
    
    short_rep = MonitoringAgent.generate_short_report(metrics, health, recs)
    assert "System Health: GOOD" in short_rep
    assert "CPU: 45.0%" in short_rep
    
    detailed_rep = MonitoringAgent.generate_detailed_report(metrics, health, recs, [metrics])
    assert "Health Score: 100/100" in detailed_rep
    assert "Used: 4096.0 MB" in detailed_rep
    assert "Latency: 10.0" in detailed_rep


def test_failure_cases(clean_monitor_env, monkeypatch):
    import psutil
    
    # 1. Missing GPU (force import error or execution exception)
    # 2. Missing temp sensor (sensors_temperatures returns AttributeError or empty)
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {}, raising=False)
    
    # 3. Network unavailable (ping exception)
    def mock_connect(self, addr):
        raise ConnectionRefusedError("Offline")
    import socket
    monkeypatch.setattr(socket.socket, "connect", mock_connect)
    
    # 4. psutil exception
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: exec("raise RuntimeError('psutil fail')"))
    
    res = MonitoringAgent.collect_metrics("monitoring")
    assert res["success"] is True
    metrics = res["metrics"]
    assert metrics["cpu_percent"] == 0.0
    assert metrics["cpu_temp"] is None
    assert metrics["gpu_usage"] == 0.0
    assert metrics["network_latency_ms"] == 5.0 # fallback default


def test_incident_detection(clean_monitor_env, monkeypatch):
    # Simulate CPU saturation (> 95%) for 5 consecutive samples
    stats = MonitoringAgent.load_stats()
    stats["samples_history"] = [{"cpu_percent": 96.0}] * 4
    MonitoringAgent.save_stats(stats)
    
    # Force the 5th sample to also be > 95%
    import psutil
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 97.0)
    
    res = MonitoringAgent.collect_metrics("monitoring")
    assert res["success"] is True
    
    # Check if incident report is written to memory database
    recall_res = MemoryService.recall(agent="coder", query="INCIDENT")
    print("RECALL RES:", recall_res)
    assert len(recall_res) > 0
    assert "Sustained CPU saturation detected" in recall_res[0]["content"]
