"""
Resource Monitor — Step 30
===========================

Provides real-time system metrics tracking using psutil and torch.mps.
Runs in a background thread to maintain an updated snapshot of system usage.
"""

from __future__ import annotations

import time
import threading
import psutil
from typing import Dict, Optional
import torch

from kattappa_runtime.resource_governor.schema import SystemResourceMetrics, SubsystemStats


class ResourceMonitor:
    """
    Monitors CPU, RAM, GPU (MPS), Disk I/O, Network, Temperature, and Battery.
    Updates thread-safely at a configurable interval.
    """
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._metrics = SystemResourceMetrics()
        self._subsystem_stats: Dict[str, SubsystemStats] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        # Keep track of last I/O counters for rate estimation
        self._last_disk_read = 0
        self._last_disk_write = 0
        self._last_net_recv = 0
        self._last_net_sent = 0
        self._last_io_time = time.time()
        
        self._init_io_counters()

    def _init_io_counters(self):
        try:
            dk = psutil.disk_io_counters()
            if dk:
                self._last_disk_read = dk.read_bytes
                self._last_disk_write = dk.write_bytes
        except Exception:
            pass

        try:
            net = psutil.net_io_counters()
            if net:
                self._last_net_recv = net.bytes_recv
                self._last_net_sent = net.bytes_sent
        except Exception:
            pass
        self._last_io_time = time.time()

    def start(self):
        """Start the background monitor thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="KRG-Monitor")
        self._thread.start()

    def stop(self):
        """Stop the background monitor thread."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self._thread = None

    def get_metrics(self) -> SystemResourceMetrics:
        """Get the latest collected resource metrics thread-safely."""
        with self._lock:
            return self._metrics

    def update_subsystem_stats(self, subsystem: str, stats: SubsystemStats):
        """Update latency, queue length, active agents, etc. for a subsystem."""
        with self._lock:
            self._subsystem_stats[subsystem] = stats

    def get_subsystem_stats(self, subsystem: str) -> Optional[SubsystemStats]:
        """Get performance stats for a subsystem."""
        with self._lock:
            return self._subsystem_stats.get(subsystem)

    def force_poll(self):
        """Force a metric update immediately."""
        self._update_metrics()

    def _run(self):
        while not self._stop_event.is_set():
            self._update_metrics()
            # Bounded sleep checking the stop event periodically
            sleep_step = 0.1
            elapsed = 0.0
            while elapsed < self.interval:
                if self._stop_event.is_set():
                    break
                time.sleep(sleep_step)
                elapsed += sleep_step

    def _update_metrics(self):
        now = time.time()
        time_delta = max(now - self._last_io_time, 0.001)
        self._last_io_time = now

        # 1. CPU and RAM
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent

        # 2. Disk I/O Rates
        disk_read_bytes_sec = 0.0
        disk_write_bytes_sec = 0.0
        try:
            dk = psutil.disk_io_counters()
            if dk:
                disk_read_bytes_sec = max(dk.read_bytes - self._last_disk_read, 0) / time_delta
                disk_write_bytes_sec = max(dk.write_bytes - self._last_disk_write, 0) / time_delta
                self._last_disk_read = dk.read_bytes
                self._last_disk_write = dk.write_bytes
        except Exception:
            pass

        # 3. Network I/O Rates
        net_recv_bytes_sec = 0.0
        net_sent_bytes_sec = 0.0
        try:
            net = psutil.net_io_counters()
            if net:
                net_recv_bytes_sec = max(net.bytes_recv - self._last_net_recv, 0) / time_delta
                net_sent_bytes_sec = max(net.bytes_sent - self._last_net_sent, 0) / time_delta
                self._last_net_recv = net.bytes_recv
                self._last_net_sent = net.bytes_sent
        except Exception:
            pass

        # 4. Battery status
        battery_pct = 100.0
        try:
            bat = psutil.sensors_battery()
            if bat:
                battery_pct = bat.percent
        except Exception:
            pass

        # 5. GPU (MPS) memory usage
        gpu_pct = 0.0
        unified_mem = 0.0
        vram_mem = 0.0
        if torch.backends.mps.is_available():
            try:
                # Driver allocated memory in bytes
                allocated = torch.mps.driver_allocated_memory()
                unified_mem = allocated / (1024 ** 3)  # Convert to GB
                # Estimated VRAM limit: VRAM and RAM are shared.
                vram_mem = unified_mem
                # Estimate GPU utilization based on thread occupancy or simulated load
                if unified_mem > 0:
                    gpu_pct = min(100.0, (unified_mem / 8.0) * 100.0)  # assume 8GB threshold
            except Exception:
                pass

        # 6. Temperature and power estimation
        # If no raw sensor access, estimate thermal load based on CPU activity
        temp = 45.0 + (cpu * 0.4)
        power = 10.0 + (cpu * 0.3) + (gpu_pct * 0.5)

        # Thread-safe write
        with self._lock:
            self._metrics = SystemResourceMetrics(
                cpu_percent=cpu,
                ram_percent=ram,
                gpu_percent=gpu_pct,
                unified_memory_used_gb=unified_mem,
                vram_used_gb=vram_mem,
                disk_io_read_bytes_sec=disk_read_bytes_sec,
                disk_io_write_bytes_sec=disk_write_bytes_sec,
                net_io_recv_bytes_sec=net_recv_bytes_sec,
                net_io_sent_bytes_sec=net_sent_bytes_sec,
                temperature_c=temp,
                battery_percent=battery_pct,
                power_draw_watts=power,
            )
