"""
File-backed isolated pytest shard launcher for Kattappa validation suite.
Eliminates command line length limits (WinError 206) by loading shard definitions
and node IDs from JSON files inside the child process.

Validates shard-definition identity against run-identity.json before execution.
"""

import sys
import os
import re
import argparse
import json
import hashlib
import tempfile
import pytest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation.pytest_result_plugin import KattappaResultPlugin

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

IDENTITY_FIELDS = [
    "run_id", "run_label", "candidate_commit",
    "collection_hash", "policy_hash",
    "manifest_core_hash", "manifest_file_hash",
    "environment_hash",
]

SHA256_FIELDS = [
    "collection_hash", "policy_hash",
    "manifest_core_hash", "manifest_file_hash",
    "environment_hash",
]


def _validate_sha256(value: str, name: str):
    """Validate a string is exactly 64 lowercase hexadecimal characters."""
    if not value:
        raise ValueError(f"SHARD_IDENTITY_INVALID: {name} is null or empty")
    if not _SHA256_RE.match(value):
        raise ValueError(
            f"SHARD_IDENTITY_INVALID: {name} is not a valid lowercase SHA-256 hex string (got {value!r})"
        )


def _validate_shard_definition(shard_data: dict):
    """Validate shard definition schema completeness and integrity."""
    # Schema version
    schema_version = shard_data.get("schema_version")
    if schema_version != 1:
        raise ValueError(
            f"SHARD_IDENTITY_INVALID: Unknown schema_version: {schema_version}"
        )

    # Required identity fields
    for field in IDENTITY_FIELDS:
        val = shard_data.get(field)
        if val is None or val == "":
            raise ValueError(
                f"SHARD_IDENTITY_INVALID: Missing or null identity field: {field}"
            )

    # SHA-256 format validation
    for field in SHA256_FIELDS:
        _validate_sha256(shard_data[field], field)

    # Node list validation
    node_ids = shard_data.get("node_ids")
    if not isinstance(node_ids, list):
        raise ValueError("SHARD_IDENTITY_INVALID: node_ids must be a list")
    if len(node_ids) == 0:
        raise ValueError("SHARD_IDENTITY_INVALID: node_ids list is empty")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("SHARD_IDENTITY_INVALID: Duplicate node IDs in shard definition")

    # Timeout validation
    timeout = shard_data.get("timeout_seconds")
    if timeout is not None:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError(f"SHARD_IDENTITY_INVALID: Invalid timeout_seconds: {timeout}")

    # Shard ID
    shard_id = shard_data.get("shard_id")
    if not shard_id:
        raise ValueError("SHARD_IDENTITY_INVALID: Missing shard_id")


def _validate_run_identity_match(shard_data: dict, run_identity: dict):
    """Compare every shared identity field between shard definition and run-identity.json."""
    for field in IDENTITY_FIELDS:
        shard_val = shard_data.get(field)
        identity_val = run_identity.get(field)
        if shard_val != identity_val:
            raise ValueError(
                f"SHARD_RUN_IDENTITY_MISMATCH: Field '{field}' mismatch: "
                f"shard={shard_val!r} vs run-identity={identity_val!r}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Execute a Kattappa test shard with file-backed node list."
    )
    parser.add_argument(
        "--shard-definition", required=True,
        help="Path to shard definition JSON file"
    )
    parser.add_argument(
        "--result-file", required=True,
        help="Path to pytest results output JSON file"
    )
    parser.add_argument(
        "--run-identity", required=False, default=None,
        help="Path to run-identity.json for cross-validation"
    )

    args = parser.parse_args()

    shard_def_path = Path(args.shard_definition)
    result_file_path = Path(args.result_file)

    if not shard_def_path.exists():
        sys.stderr.write(f"Shard definition file not found: {shard_def_path}\n")
        sys.exit(1)

    shard_data = json.loads(shard_def_path.read_text(encoding="utf-8"))

    # Validate shard definition schema
    try:
        _validate_shard_definition(shard_data)
    except ValueError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)

    # Validate against run-identity.json if provided
    if args.run_identity:
        identity_path = Path(args.run_identity)
        if not identity_path.exists():
            sys.stderr.write(f"Run identity file not found: {identity_path}\n")
            sys.exit(1)
        run_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        try:
            _validate_run_identity_match(shard_data, run_identity)
        except ValueError as e:
            sys.stderr.write(f"{e}\n")
            sys.exit(1)

    # Compute shard definition hash
    shard_def_bytes = shard_def_path.read_bytes()
    shard_definition_sha256 = hashlib.sha256(shard_def_bytes).hexdigest()

    # Extract details
    shard_id = shard_data["shard_id"]
    node_ids = shard_data["node_ids"]

    # Set environment variables for run details and node ID filtering
    os.environ["KATTAPPA_TEST_MODE"] = "true"
    os.environ["KATTAPPA_SHARD_ID"] = shard_id
    os.environ["KATTAPPA_RUN_ID"] = shard_data.get("run_id", "")
    os.environ["KATTAPPA_CANDIDATE_COMMIT"] = shard_data.get("candidate_commit", "")

    # Write expected-node-ids.json atomically to shard dir
    shard_dir = shard_def_path.parent
    node_ids_file = shard_dir / "expected-node-ids.json"

    # Remove any stale file
    if node_ids_file.exists():
        node_ids_file.unlink()

    # Write atomically
    node_ids_tmp = node_ids_file.with_suffix(".json.tmp")
    node_ids_content = json.dumps(node_ids, indent=2)
    with open(node_ids_tmp, "w", encoding="utf-8") as f:
        f.write(node_ids_content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(node_ids_tmp, node_ids_file)

    # Reopen and validate
    reopened = json.loads(node_ids_file.read_text(encoding="utf-8"))
    if reopened != node_ids:
        sys.stderr.write("expected-node-ids.json content mismatch after write\n")
        sys.exit(1)

    # Hash expected-node-ids
    expected_node_ids_sha256 = hashlib.sha256(
        node_ids_file.read_bytes()
    ).hexdigest()

    os.environ["KATTAPPA_SHARD_NODE_IDS_FILE"] = str(node_ids_file)

    # Unique files to pass to pytest for collection speed
    unique_files = sorted(list(set(node.split("::")[0] for node in node_ids)))

    # Construct pytest args in memory — disable cacheprovider and reset testpaths so explicit file args work
    pytest_args = [
        "-o", "testpaths=",
        "-p", "no:cacheprovider",
        "-s",
        "-v"
    ] + unique_files

    # Instantiate and register plugin — use correct keyword: output_file
    plugin = KattappaResultPlugin(output_file=result_file_path)

    # Run pytest.main inside child process
    exit_code = int(pytest.main(pytest_args, plugins=[plugin]))

    # Inject identity and hash fields into the result file
    if result_file_path.exists():
        try:
            result_data = json.loads(result_file_path.read_text(encoding="utf-8"))
            # Add validated identity
            for field in IDENTITY_FIELDS:
                result_data[field] = shard_data[field]
            result_data["shard_id"] = shard_id
            result_data["shard_definition_sha256"] = shard_definition_sha256
            result_data["expected_node_ids_sha256"] = expected_node_ids_sha256
            # Re-write atomically
            tmp_result = result_file_path.with_suffix(".json.tmp")
            with open(tmp_result, "w", encoding="utf-8") as f:
                json.dump(result_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_result, result_file_path)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to inject identity into result: {e}\n")

    # Ensure output files are flushed
    sys.stdout.flush()
    sys.stderr.flush()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
