"""
File-backed isolated pytest shard launcher for Kattappa validation suite.
Eliminates command line length limits (WinError 206) by loading shard definitions
and node IDs from JSON files inside the child process.
"""

import sys
import os
import argparse
import json
import pytest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation.pytest_result_plugin import KattappaResultPlugin


def main():
    parser = argparse.ArgumentParser(description="Execute a Kattappa test shard with file-backed node list.")
    parser.add_argument("--shard-definition", required=True, help="Path to shard definition JSON file")
    parser.add_argument("--result-file", required=True, help="Path to pytest results output JSON file")

    args = parser.parse_args()

    shard_def_path = Path(args.shard_definition)
    result_file_path = Path(args.result_file)

    if not shard_def_path.exists():
        sys.stderr.write(f"Shard definition file not found: {shard_def_path}\n")
        sys.exit(1)

    shard_data = json.loads(shard_def_path.read_text(encoding="utf-8"))

    # Extract details
    shard_id = shard_data.get("shard_id", "unknown_shard")
    node_ids = shard_data.get("node_ids", [])
    run_id = shard_data.get("run_id", "")
    candidate_commit = shard_data.get("candidate_commit", "")

    # Set environment variables for run details and node ID filtering
    os.environ["KATTAPPA_TEST_MODE"] = "true"
    os.environ["KATTAPPA_SHARD_ID"] = shard_id
    if run_id:
        os.environ["KATTAPPA_RUN_ID"] = run_id
    if candidate_commit:
        os.environ["KATTAPPA_CANDIDATE_COMMIT"] = candidate_commit

    # Store node_ids in a temp file for plugin node filtering
    node_ids_file = shard_def_path.parent / "shard_node_ids.json"
    node_ids_file.write_text(json.dumps(node_ids, indent=2), encoding="utf-8")
    os.environ["KATTAPPA_SHARD_NODE_IDS_FILE"] = str(node_ids_file)

    # Unique files to pass to pytest for collection speed
    unique_files = sorted(list(set(node.split("::")[0] for node in node_ids)))

    # Construct pytest args in memory
    pytest_args = [
        "-o", "cache_dir=/dev/null",
        "-s",
        "-v"
    ] + unique_files

    # Instantiate and register plugin
    plugin = KattappaResultPlugin(result_file_path=str(result_file_path))

    # Run pytest.main inside child process
    exit_code = int(pytest.main(pytest_args, plugins=[plugin]))

    # Ensure output files are flushed
    sys.stdout.flush()
    sys.stderr.flush()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
