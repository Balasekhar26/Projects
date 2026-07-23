"""
K-HIM OS-Level Process Tree Memory Supervisor for Windows (Job Object Enforcement).
Fail-closed production supervisor enforcing process tree physical RAM working set ceilings
(8,000,000,000 decimal bytes) using native Windows Job Object accounting and process group tracking.
"""

from __future__ import annotations

import os
import sys
import ctypes
from ctypes import wintypes
from typing import Dict, Any

HARD_CEILING_BYTES = 8_000_000_000      # 8.0 GB
DEEP_REASONING_BYTES = 7_300_000_000   # 7.3 GB
INTERACTIVE_TARGET_BYTES = 6_200_000_000# 6.2 GB
EMERGENCY_RESERVE_BYTES = 700_000_000   # 700 MB


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJobMemorySupervisor:
    """Fail-closed Windows Job Object memory supervisor enforcing process tree RAM limits."""

    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    JobObjectExtendedLimitInformation = 9

    def __init__(self, limit_bytes: int = HARD_CEILING_BYTES):
        self.limit_bytes = limit_bytes
        self._job_handle = None
        self._is_windows = sys.platform.startswith("win")
        self.enforcement_active = False

        if self._is_windows:
            self._init_job_object()

    def _init_job_object(self):
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.GetLastError.restype = wintypes.DWORD

            self._job_handle = kernel32.CreateJobObjectW(None, "KattappaProcessGroupJob")
            if not self._job_handle:
                return

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_JOB_MEMORY
            info.JobMemoryLimit = self.limit_bytes

            res = kernel32.SetInformationJobObject(
                self._job_handle,
                self.JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info)
            )
            if not res:
                return

            current_proc = kernel32.GetCurrentProcess()
            assign_res = kernel32.AssignProcessToJobObject(self._job_handle, current_proc)
            self.enforcement_active = bool(assign_res)
        except Exception:
            self.enforcement_active = False

    def get_process_tree_memory(self) -> Dict[str, Any]:
        """Measures working set and committed bytes. Fails closed if telemetry is unavailable."""
        try:
            import psutil
            parent = psutil.Process()
            procs = [parent] + parent.children(recursive=True)
            total_rss = sum(p.memory_info().rss for p in procs if p.is_running())
            total_vms = sum(p.memory_info().vms for p in procs if p.is_running())

            return {
                "measurement_valid": True,
                "enforcement_active": self.enforcement_active,
                "process_count": len(procs),
                "total_rss_bytes": total_rss,
                "total_vms_bytes": total_vms,
                "within_hard_ceiling": total_rss < self.limit_bytes,
                "within_interactive_target": total_rss < INTERACTIVE_TARGET_BYTES,
                "hard_ceiling_bytes": self.limit_bytes
            }
        except Exception as exc:
            # FAIL CLOSED: When measurement fails, return measurement_valid=False and within_hard_ceiling=False
            return {
                "measurement_valid": False,
                "enforcement_active": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "within_hard_ceiling": False,
                "hard_ceiling_bytes": self.limit_bytes
            }

    def close(self):
        """Idempotent handle cleanup."""
        if self._job_handle and self._is_windows:
            try:
                ctypes.windll.kernel32.CloseHandle(self._job_handle)
            except Exception:
                pass
            self._job_handle = None
            self.enforcement_active = False
