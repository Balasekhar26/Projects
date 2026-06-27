"""
Resource Monitor — Step 30 (Safety Controller hardening)
=========================================================

Provides real-time system metrics tracking using psutil, subprocess/sysctl, and torch.mps.
Runs in a background thread to maintain an updated snapshot of system usage,
with specific enhancements for Apple Silicon (swap files, memory pressure, compressed memory, pageouts rate).
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import Dict, Optional

import psutil
import torch

from kattappa_runtime.resource_governor.schema import (
    AppleSiliconPressure,
    SubsystemStats,
    SystemResourceMetrics,
)


class ResourceMonitor:
    """
    Monitors CPU, RAM, GPU (MPS), Disk I/O, Network, Temperature, Battery,
    and Apple Silicon memory/swap pressure metrics (including pageouts/swapouts rates).
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

        # Mach VM Stats tracking
        self._last_pageouts = 0
        self._last_swapouts = 0
        self._last_vm_stat_time = time.time()
        
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

        # Mach VM statistics initialization
        vm_stats = self._get_macos_vm_stat()
        self._last_pageouts = vm_stats["pageouts"]
        self._last_swapouts = vm_stats["swapouts"]
        self._last_vm_stat_time = time.time()
        
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

    def _get_macos_swap(self) -> tuple[float, float, int]:
        """Reads macOS swap metrics. Returns (used_gb, total_gb, file_count)."""
        used_gb, total_gb, file_count = 0.0, 0.0, 0
        try:
            # Parse sysctl vm.swapusage
            out = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
            m = re.search(r"total\s*=\s*([\d.]+)M\s*used\s*=\s*([\d.]+)M", out)
            if m:
                total_gb = float(m.group(1)) / 1024.0
                used_gb = float(m.group(2)) / 1024.0
        except Exception:
            try:
                sw = psutil.swap_memory()
                total_gb = sw.total / (1024**3)
                used_gb = sw.used / (1024**3)
            except Exception:
                pass

        # Count swap files in common macOS locations
        try:
            for path in ["/System/Volumes/VM", "/private/var/vm"]:
                if os.path.exists(path):
                    files = [f for f in os.listdir(path) if f.startswith("swapfile")]
                    if files:
                        file_count = len(files)
                        break
        except Exception:
            pass

        return used_gb, total_gb, file_count

    def _get_macos_vm_stat(self) -> dict[str, int]:
        """Reads Mach VM Stats from vm_stat."""
        stats = {"pageouts": 0, "swapouts": 0, "compressed_pages": 0, "page_size": 4096}
        try:
            out = subprocess.check_output(["vm_stat"], text=True)
            m_page = re.search(r"page size of (\d+) bytes", out)
            if m_page:
                stats["page_size"] = int(m_page.group(1))

            m_comp = re.search(r"Pages occupied by compressor:\s*(\d+)", out)
            if m_comp:
                stats["compressed_pages"] = int(m_comp.group(1))

            m_pageouts = re.search(r"Pages pageout:\s*(\d+)", out)
            if not m_pageouts:
                # Alternate header name in some versions
                m_pageouts = re.search(r"Pageouts:\s*(\d+)", out)
            if m_pageouts:
                stats["pageouts"] = int(m_pageouts.group(1))

            m_swapouts = re.search(r"Swapouts:\s*(\d+)", out)
            if m_swapouts:
                stats["swapouts"] = int(m_swapouts.group(1))
        except Exception:
            pass
        return stats

    def _get_macos_memory_pressure(self) -> AppleSiliconPressure:
        """Reads macOS memory pressure status level and maps it to AppleSiliconPressure."""
        try:
            out = subprocess.check_output(["sysctl", "-n", "kern.memorystatus_level"], text=True).strip()
            level = int(out)
            if level >= 80:
                return AppleSiliconPressure.NOMINAL
            elif level >= 50:
                return AppleSiliconPressure.WARN
            else:
                return AppleSiliconPressure.CRITICAL
        except Exception:
            pass
        return AppleSiliconPressure.NOMINAL

    def _update_metrics(self):
        try:
            hb_path = os.path.expanduser("~/Desktop/kattappa_heartbeat_monitor.txt")
            with open(hb_path, "w") as f:
                f.write(f"{time.time()}\n")
        except Exception:
            pass

        now = time.time()
        time_delta = max(now - self._last_io_time, 0.001)
        self._last_io_time = now

        # 1. CPU and RAM
        cpu = psutil.cpu_percent(interval=None)
        vmem = psutil.virtual_memory()
        ram = vmem.percent
        total_ram_bytes = vmem.total

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

        # 5. GPU (MPS) memory usage & recommended limit
        gpu_pct = 0.0
        unified_mem = 0.0
        vram_mem = 0.0
        mps_recommended_max = 0.0
        if torch.backends.mps.is_available():
            try:
                allocated = torch.mps.driver_allocated_memory()
                unified_mem = allocated / (1024 ** 3)
                vram_mem = unified_mem
                
                if hasattr(torch.mps, "recommended_max_memory"):
                    mps_recommended_max = torch.mps.recommended_max_memory() / (1024 ** 3)
                else:
                    # Estimate based on 16GB default or sysctl
                    mps_recommended_max = (total_ram_bytes * 0.6) / (1024 ** 3)
                
                if mps_recommended_max > 0:
                    gpu_pct = min(100.0, (unified_mem / mps_recommended_max) * 100.0)
            except Exception:
                pass

        # 6. Temperature and power estimation
        temp = 45.0 + (cpu * 0.4)
        power = 10.0 + (cpu * 0.3) + (gpu_pct * 0.5)

        # 7. macOS specific metrics (swap, compressed, memory pressure level, SSD free)
        swap_used, swap_total, swap_files = self._get_macos_swap()
        mem_pressure = self._get_macos_memory_pressure()
        
        # Parse Mach VM stats & calculate rate
        vm_stats = self._get_macos_vm_stat()
        vm_now = time.time()
        vm_delta = max(vm_now - self._last_vm_stat_time, 0.001)
        self._last_vm_stat_time = vm_now

        pageouts_rate = max(vm_stats["pageouts"] - self._last_pageouts, 0) / vm_delta
        swapouts_rate = max(vm_stats["swapouts"] - self._last_swapouts, 0) / vm_delta

        self._last_pageouts = vm_stats["pageouts"]
        self._last_swapouts = vm_stats["swapouts"]

        compressed_pct = 0.0
        if total_ram_bytes > 0:
            compressed_pct = (vm_stats["compressed_pages"] * vm_stats["page_size"] / total_ram_bytes) * 100.0

        ssd_free = 500.0
        try:
            ssd_free = psutil.disk_usage('/').free / (1024 ** 3)
        except Exception:
            pass

        # Thread-safe write
        with self._lock:
            self._metrics = SystemResourceMetrics(
                cpu_percent=cpu,
                ram_percent=ram,
                gpu_percent=gpu_pct,
                unified_memory_used_gb=unified_mem,
                vram_used_gb=vram_mem,
                mps_recommended_max_memory_gb=mps_recommended_max,
                disk_io_read_bytes_sec=disk_read_bytes_sec,
                disk_io_write_bytes_sec=disk_write_bytes_sec,
                net_io_recv_bytes_sec=net_recv_bytes_sec,
                net_io_sent_bytes_sec=net_sent_bytes_sec,
                temperature_c=temp,
                battery_percent=battery_pct,
                power_draw_watts=power,
                swap_used_gb=swap_used,
                swap_total_gb=swap_total,
                swap_file_count=swap_files,
                compressed_memory_pct=compressed_pct,
                memory_pressure=mem_pressure,
                ssd_free_gb=ssd_free,
                pageouts_per_sec=pageouts_rate,
                swapouts_per_sec=swapouts_rate
            )
