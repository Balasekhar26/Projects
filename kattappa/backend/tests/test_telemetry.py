import time
from backend.core.ledger.telemetry.metrics_collector import MetricsCollector
from backend.core.ledger.telemetry.telemetry_service import TelemetryService


def test_metrics_collector():
    collector = MetricsCollector(window_size=3)

    # Check empty
    assert collector.get_values("cpu_usage") == []

    # Record observations
    collector.record("cpu_usage", 10.0)
    collector.record("cpu_usage", 20.0)
    collector.record("cpu_usage", 30.0)

    assert collector.get_values("cpu_usage") == [10.0, 20.0, 30.0]

    # Window limit eviction
    collector.record("cpu_usage", 40.0)
    assert collector.get_values("cpu_usage") == [20.0, 30.0, 40.0]

    # Record with custom metric name
    collector.record("custom_metric", 100.0)
    assert collector.get_values("custom_metric") == [100.0]


def test_metrics_collector_since():
    collector = MetricsCollector()
    t0 = time.time()
    collector.record("latency", 1.0)
    time.sleep(0.01)
    t1 = time.time()
    collector.record("latency", 2.0)

    # Since t0
    assert collector.get_values_since("latency", t0) == [1.0, 2.0]

    # Since t1
    assert collector.get_values_since("latency", t1) == [2.0]

    # Clear
    collector.clear()
    assert collector.get_values("latency") == []


def test_telemetry_service_stats():
    collector = MetricsCollector()
    service = TelemetryService(collector)

    # Empty stats
    empty_stats = service.get_metric_stats("cpu_usage")
    assert empty_stats["count"] == 0.0
    assert empty_stats["mean"] == 0.0

    # Populate values: 10.0, 20.0, 30.0, 40.0, 50.0
    for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
        collector.record("cpu_usage", v)

    stats = service.get_metric_stats("cpu_usage")
    assert stats["count"] == 5.0
    assert stats["sum"] == 150.0
    assert stats["mean"] == 30.0
    assert stats["p50"] == 30.0

    # Percentiles:
    # 5 items -> sorted: 10, 20, 30, 40, 50
    # k = 4 * 0.9 = 3.6 -> between idx 3 (40) and 4 (50)
    # 40 * (4 - 3.6) + 50 * (3.6 - 3) = 40 * 0.4 + 50 * 0.6 = 16 + 30 = 46.0
    assert stats["p90"] == 46.0

    # Report generation
    report = service.generate_report()
    assert "cpu_usage" in report
    assert report["cpu_usage"]["mean"] == 30.0
    assert "perceive_latency" in report
    assert report["perceive_latency"]["count"] == 0.0
