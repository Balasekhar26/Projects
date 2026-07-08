import math
from typing import Dict, Any, List
from backend.core.ledger.telemetry.metrics_collector import MetricsCollector


class TelemetryService:
    def __init__(self, collector: MetricsCollector) -> None:
        self.collector = collector

    @staticmethod
    def _percentile(data: List[float], percent: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (percent / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(sorted_data[int(k)])
        d0 = sorted_data[int(f)] * (c - k)
        d1 = sorted_data[int(c)] * (k - f)
        return float(d0 + d1)

    def get_metric_stats(self, metric_name: str) -> Dict[str, float]:
        """Calculates statistics (mean, sum, p50, p90, p99) for the given metric."""
        values = self.collector.get_values(metric_name)
        if not values:
            return {
                "count": 0.0,
                "sum": 0.0,
                "mean": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p99": 0.0,
            }

        val_sum = sum(values)
        val_count = len(values)
        return {
            "count": float(val_count),
            "sum": float(val_sum),
            "mean": float(val_sum / val_count),
            "p50": self._percentile(values, 50.0),
            "p90": self._percentile(values, 90.0),
            "p99": self._percentile(values, 99.0),
        }

    def generate_report(self) -> Dict[str, Any]:
        """Generates a complete rolling telemetry metrics report."""
        report = {}
        metrics_to_report = [
            "perceive_latency",
            "retrieve_latency",
            "reason_latency",
            "plan_latency",
            "act_latency",
            "learn_latency",
            "cpu_usage",
            "memory_usage",
            "tokens_consumed",
            "active_goals",
            "interrupted_goals",
        ]
        for name in metrics_to_report:
            report[name] = self.get_metric_stats(name)
        return report
