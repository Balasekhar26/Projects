import time
import threading
from collections import deque
from typing import Dict, List


class MetricsCollector:
    def __init__(self, window_size: int = 100) -> None:
        self._lock = threading.Lock()
        self._window_size = window_size

        self._metrics: Dict[str, deque] = {
            "perceive_latency": deque(maxlen=window_size),
            "retrieve_latency": deque(maxlen=window_size),
            "reason_latency": deque(maxlen=window_size),
            "plan_latency": deque(maxlen=window_size),
            "act_latency": deque(maxlen=window_size),
            "learn_latency": deque(maxlen=window_size),
            "cpu_usage": deque(maxlen=window_size),
            "memory_usage": deque(maxlen=window_size),
            "tokens_consumed": deque(maxlen=window_size),
            "active_goals": deque(maxlen=window_size),
            "interrupted_goals": deque(maxlen=window_size),
        }

    def record(self, metric_name: str, value: float, metadata: dict | None = None) -> None:
        """Records an observation for the given metric and persists to SQLite if available."""
        now = time.time()
        with self._lock:
            if metric_name not in self._metrics:
                self._metrics[metric_name] = deque(maxlen=self._window_size)
            self._metrics[metric_name].append((now, value))

        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                KERNEL.ledger.record_metric(now, metric_name, value, metadata)
        except Exception:
            pass

    def get_values(self, metric_name: str) -> List[float]:
        """Returns the collected list of values for the given metric name."""
        with self._lock:
            if metric_name in self._metrics and len(self._metrics[metric_name]) > 0:
                return [val for _, val in self._metrics[metric_name]]

        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                db_values = KERNEL.ledger.get_metric_values(metric_name)
                if db_values:
                    return [val for _, val in db_values]
        except Exception:
            pass

        with self._lock:
            if metric_name not in self._metrics:
                return []
            return [val for _, val in self._metrics[metric_name]]

    def get_values_since(self, metric_name: str, since_timestamp: float) -> List[float]:
        """Returns the collected list of values since the target timestamp."""
        with self._lock:
            if metric_name in self._metrics and len(self._metrics[metric_name]) > 0:
                return [val for ts, val in self._metrics[metric_name] if ts >= since_timestamp]

        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                db_values = KERNEL.ledger.get_metric_values(metric_name, since_timestamp)
                if db_values:
                    return [val for _, val in db_values]
        except Exception:
            pass

        with self._lock:
            if metric_name not in self._metrics:
                return []
            return [
                val for ts, val in self._metrics[metric_name] if ts >= since_timestamp
            ]

    def clear(self) -> None:
        """Clears all stored metrics."""
        with self._lock:
            for metric in self._metrics.values():
                metric.clear()
        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
                if hasattr(KERNEL.ledger, "clear_metrics"):
                    KERNEL.ledger.clear_metrics()
        except Exception:
            pass
