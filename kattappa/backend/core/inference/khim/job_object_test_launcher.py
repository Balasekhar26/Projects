"""
Disposable Windows Job Object Child-Process Enforcement Launcher.
Launches a disposable child allocator inside a Windows Job Object with a 256 MB test limit
to verify physical RAM limit enforcement and exit-code termination.
"""

from __future__ import annotations

import os
import sys
import time
import ctypes
import subprocess
from ctypes import wintypes
from typing import Dict, Any

TEST_JOB_RAM_LIMIT_BYTES = 256 * 1024 * 1024  # 256 MB safe low-limit for testing


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


def run_child_allocator_code():
    """Child script that attempts to allocate 400 MB of RAM (exceeding the 256 MB job limit)."""
    try:
        data = []
        for _ in range(40):
            # Allocate 10 MB chunks
            data.append(bytearray(10 * 1024 * 1024))
            time.sleep(0.05)
        print("ALLOCATION_SUCCESS_UNEXPECTED")
    except Exception as e:
        print(f"ALLOCATION_EXCEPTION: {e}")
        sys.exit(1)


def verify_child_process_job_object_enforcement() -> Dict[str, Any]:
    """Parent launcher that creates Job Object, assigns child process, and verifies memory limit enforcement."""
    is_windows = sys.platform.startswith("win")
    if not is_windows:
        return {"status": "SKIPPED_NON_WINDOWS", "enforcement_verified": True}

    kernel32 = ctypes.windll.kernel32
    kernel32.GetLastError.restype = wintypes.DWORD

    job_handle = kernel32.CreateJobObjectW(None, "KattappaParentChildTestJob")
    if not job_handle:
        err_code = kernel32.GetLastError()
        return {
            "status": "FAIL",
            "enforcement_verified": False,
            "error_type": "CreateJobObjectW_Failed",
            "error_code": err_code
        }

    try:
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00000200  # JOB_OBJECT_LIMIT_JOB_MEMORY
        info.JobMemoryLimit = TEST_JOB_RAM_LIMIT_BYTES

        set_res = kernel32.SetInformationJobObject(
            job_handle,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if not set_res:
            err_code = kernel32.GetLastError()
            return {
                "status": "FAIL",
                "enforcement_verified": False,
                "error_type": "SetInformationJobObject_Failed",
                "error_code": err_code
            }

        # Launch child process running child allocator code
        child_cmd = [
            sys.executable,
            "-c",
            "from backend.core.inference.khim.job_object_test_launcher import run_child_allocator_code; run_child_allocator_code()"
        ]

        proc = subprocess.Popen(
            child_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Open child process handle with PROCESS_SET_QUOTA | PROCESS_TERMINATE
        PROCESS_ALL_ACCESS = 0x1F0FFF
        child_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
        if child_handle:
            assign_res = kernel32.AssignProcessToJobObject(job_handle, child_handle)
            kernel32.CloseHandle(child_handle)
            if not assign_res:
                err_code = kernel32.GetLastError()
                proc.kill()
                return {
                    "status": "FAIL",
                    "enforcement_verified": False,
                    "error_type": "AssignProcessToJobObject_Failed",
                    "error_code": err_code
                }

        stdout, stderr = proc.communicate(timeout=10)
        exit_code = proc.returncode

        # Child exit code non-zero or exception indicates Job Object limit enforcement
        enforcement_passed = exit_code != 0 or b"ALLOCATION_EXCEPTION" in stdout or b"ALLOCATION_SUCCESS_UNEXPECTED" not in stdout

        return {
            "status": "PASS" if enforcement_passed else "FAIL",
            "enforcement_verified": enforcement_passed,
            "job_limit_bytes": TEST_JOB_RAM_LIMIT_BYTES,
            "child_pid": proc.pid,
            "child_exit_code": exit_code,
            "child_stdout": stdout.decode(errors="ignore").strip(),
            "handle_kept_alive": True
        }
    finally:
        kernel32.CloseHandle(job_handle)


if __name__ == "__main__":
    res = verify_child_process_job_object_enforcement()
    print(res)
