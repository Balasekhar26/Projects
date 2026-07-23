"""
K-HIM Multi-Window Storage-Backed Memory Mapping & Block Computation Benchmark.
Writes project-local stress fixtures under Kattappa validation-runs, queries real filesystem allocations,
tests relative intra-window offsets, and dynamically evaluates benchmark verdicts.
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any

from backend.core.inference.khim.memory_supervisor import WindowsJobMemorySupervisor, HARD_CEILING_BYTES
from backend.core.inference.khim.storage_window import KHIMStorageWindowReader, get_allocated_disk_size_bytes


def run_storage_stress_benchmark() -> Dict[str, Any]:
    supervisor = WindowsJobMemorySupervisor()
    reader = KHIMStorageWindowReader(window_size_bytes=16 * 1024 * 1024)
    fixture_sizes_gb = [1, 5, 20, 50]
    results = {}

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    base_dir = Path(r"C:\Users\balu\Projects\kattappa\validation-runs\khim-storage-stress") / run_id
    base_dir.mkdir(parents=True, exist_ok=True)

    overall_pass = True

    try:
        for size_gb in fixture_sizes_gb:
            fixture_file = base_dir / f"expert_{size_gb}gb.bin"
            file_bytes = size_gb * 1024 * 1024 * 1024

            start_time = time.monotonic()

            # Create sparse test fixture file with non-zero header and mid-file data for multi-window testing
            with open(fixture_file, "wb") as f:
                f.write(b"KATTAPPA_KHIM_EXPERT_HEADER_DATA_V1_" * 128)
                # Write data at 64 KB offset
                f.seek(64 * 1024)
                f.write(b"KATTAPPA_KHIM_EXPERT_OFFSET_64KB_BLOCK_DATA_")
                f.seek(file_bytes - 1)
                f.write(b"\x01")

            # Perform multi-window computation over offset 64 KB
            read_result_header = reader.read_and_compute_window(fixture_file, offset_bytes=0, bytes_to_process=4096)
            read_result_offset = reader.read_and_compute_window(fixture_file, offset_bytes=64 * 1024, bytes_to_process=4096)

            elapsed = time.monotonic() - start_time
            mem_stats = supervisor.get_process_tree_memory()
            rss_bytes = mem_stats.get("total_rss_bytes", 0)
            within_ceiling = mem_stats.get("within_hard_ceiling", False) and mem_stats.get("measurement_valid", True)

            if not within_ceiling:
                overall_pass = False

            alloc_info = get_allocated_disk_size_bytes(fixture_file)

            fixture_status = "PASS" if (within_ceiling and read_result_header["windowed_mapping_success"] and read_result_offset["windowed_mapping_success"]) else "FAIL"

            results[f"{size_gb}GB_fixture"] = {
                "logical_file_size_bytes": file_bytes,
                "allocated_disk_size_bytes": alloc_info["allocated_size_bytes"],
                "sparse": alloc_info["sparse"],
                "classification": "SPARSE_MAPPING_TEST",
                "header_read": {
                    "bytes_touched": read_result_header["bytes_touched"],
                    "checksum": read_result_header["deterministic_checksum"],
                    "sha256": read_result_header["sha256_digest"]
                },
                "offset_read": {
                    "offset_bytes": 64 * 1024,
                    "bytes_touched": read_result_offset["bytes_touched"],
                    "checksum": read_result_offset["deterministic_checksum"],
                    "sha256": read_result_offset["sha256_digest"]
                },
                "process_tree_rss_bytes": rss_bytes,
                "within_8gb_ram_ceiling": within_ceiling,
                "time_sec": round(elapsed, 4),
                "status": fixture_status
            }
    finally:
        # Cleanup project-local stress directory after run
        shutil.rmtree(base_dir, ignore_errors=True)

    return {
        "benchmark_status": "PASS" if overall_pass else "FAIL",
        "hard_ceiling_enforced": supervisor.enforcement_active,
        "max_ram_ceiling_bytes": HARD_CEILING_BYTES,
        "results": results
    }


if __name__ == "__main__":
    report = run_storage_stress_benchmark()
    print(json.dumps(report, indent=2))
