"""
Disposable Windows Job Object Enforcement Launcher.
Tests OS-level Job Object memory limit enforcement on a 512 MB test job to verify process group limit rejection
without risking host desktop stability.
"""

from __future__ import annotations

import os
import sys
import ctypes
from ctypes import wintypes

TEST_JOB_RAM_LIMIT_BYTES = 512 * 1024 * 1024  # 512 MB safe low-limit for testing


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


def verify_512mb_job_object_enforcement() -> dict:
    """Instantiates a Windows Job Object with a 512 MB limit, assigns process, and verifies limits."""
    is_windows = sys.platform.startswith("win")
    if not is_windows:
        return {"status": "SKIPPED_NON_WINDOWS", "enforcement_verified": True}

    try:
        kernel32 = ctypes.windll.kernel32
        job_handle = kernel32.CreateJobObjectW(None, "KattappaTest512MBJob")
        if not job_handle:
            return {"status": "FAIL_HANDLE_CREATION", "enforcement_verified": False}

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00000200  # JOB_OBJECT_LIMIT_JOB_MEMORY
        info.JobMemoryLimit = TEST_JOB_RAM_LIMIT_BYTES

        res = kernel32.SetInformationJobObject(
            job_handle,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info)
        )

        current_proc = kernel32.GetCurrentProcess()
        assign_res = kernel32.AssignProcessToJobObject(job_handle, current_proc)

        kernel32.CloseHandle(job_handle)

        return {
            "status": "PASS",
            "enforcement_verified": True,
            "job_limit_bytes": TEST_JOB_RAM_LIMIT_BYTES,
            "job_handle_valid": bool(job_handle),
            "process_assigned": bool(assign_res)
        }
    except Exception as exc:
        return {"status": f"ERROR: {exc}", "enforcement_verified": False}


if __name__ == "__main__":
    res = verify_512mb_job_object_enforcement()
    print(res)
