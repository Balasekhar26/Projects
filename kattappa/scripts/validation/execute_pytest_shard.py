"""
File-backed isolated pytest shard launcher for Kattappa validation suite.
Eliminates command line length limits (WinError 206) by loading shard definitions
and node IDs from JSON files inside the child process.

Validates shard-definition identity against run-identity.json before execution.
Enforces fail-closed result identity injection and collection-set verification.
"""

import sys
import os
import re
import argparse
import json
import hashlib
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

VALID_RUN_LABELS = {"A", "B", "C", "D", "T", "SUPERBENCH", "LOCAL_DEV"}


def _validate_sha256(value: str, name: str):
    """Validate a string is exactly 64 lowercase hexadecimal characters."""
    if not value:
        raise ValueError(f"SHARD_IDENTITY_INVALID: {name} is null or empty")
    if not _SHA256_RE.match(value):
        raise ValueError(
            f"SHARD_IDENTITY_INVALID: {name} is not a valid lowercase SHA-256 hex string (got {value!r})"
        )


def _validate_run_identity_structure(run_identity: dict):
    """Independently validate structure and format of run-identity.json."""
    if not isinstance(run_identity, dict):
        raise ValueError("RUN_IDENTITY_MALFORMED: run-identity content must be a JSON object")

    # Required fields presence and types
    for field in IDENTITY_FIELDS:
        val = run_identity.get(field)
        if val is None or val == "":
            raise ValueError(f"RUN_IDENTITY_MALFORMED: Missing or empty identity field '{field}'")
        if not isinstance(val, str):
            raise ValueError(f"RUN_IDENTITY_MALFORMED: Identity field '{field}' must be a string")

    # Non-empty run_id and candidate_commit
    if not run_identity["run_id"].strip():
        raise ValueError("RUN_IDENTITY_MALFORMED: run_id is empty")

    # Run label check
    if run_identity["run_label"] not in VALID_RUN_LABELS:
        raise ValueError(f"RUN_IDENTITY_MALFORMED: Unknown run_label '{run_identity['run_label']}'")

    # Candidate commit format (must be 64-char hex or 40-char git commit)
    commit = run_identity["candidate_commit"].strip()
    if not re.match(r"^[0-9a-fA-F]{40}$", commit) and not re.match(r"^[0-9a-fA-F]{64}$", commit):
        raise ValueError(f"RUN_IDENTITY_MALFORMED: candidate_commit '{commit}' is invalid format")

    # SHA-256 fields
    for field in SHA256_FIELDS:
        _validate_sha256(run_identity[field], f"run_identity.{field}")


def _validate_shard_definition(shard_data: dict):
    """Validate shard definition schema completeness and integrity."""
    schema_version = shard_data.get("schema_version")
    if schema_version != 1:
        raise ValueError(
            f"SHARD_IDENTITY_INVALID: Unknown schema_version: {schema_version}"
        )

    for field in IDENTITY_FIELDS:
        val = shard_data.get(field)
        if val is None or val == "":
            raise ValueError(
                f"SHARD_IDENTITY_INVALID: Missing or null identity field: {field}"
            )

    for field in SHA256_FIELDS:
        _validate_sha256(shard_data[field], field)

    node_ids = shard_data.get("node_ids")
    if not isinstance(node_ids, list):
        raise ValueError("SHARD_IDENTITY_INVALID: node_ids must be a list")
    if len(node_ids) == 0:
        raise ValueError("SHARD_IDENTITY_INVALID: node_ids list is empty")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("SHARD_IDENTITY_INVALID: Duplicate node IDs in shard definition")

    timeout = shard_data.get("timeout_seconds")
    if timeout is not None:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError(f"SHARD_IDENTITY_INVALID: Invalid timeout_seconds: {timeout}")

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
    parser.add_argument(
        "--diagnostic-mode", action="store_true", default=False,
        help="Allow running without --run-identity in standalone unit tests"
    )

    args = parser.parse_args()

    shard_def_path = Path(args.shard_definition)
    result_file_path = Path(args.result_file)

    if not shard_def_path.exists():
        sys.stderr.write(f"Shard definition file not found: {shard_def_path}\n")
        sys.exit(1)

    # Mandatory run-identity check
    if not args.run_identity and not args.diagnostic_mode:
        sys.stderr.write("RUN_IDENTITY_REQUIRED: --run-identity parameter is mandatory for official execution\n")
        sys.exit(1)

    shard_data = json.loads(shard_def_path.read_text(encoding="utf-8"))

    try:
        _validate_shard_definition(shard_data)
    except ValueError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)

    # Validate against run-identity.json
    if args.run_identity:
        identity_path = Path(args.run_identity)
        if not identity_path.exists():
            sys.stderr.write(f"RUN_IDENTITY_REQUIRED: Run identity file not found: {identity_path}\n")
            sys.exit(1)
        try:
            run_identity = json.loads(identity_path.read_text(encoding="utf-8"))
            _validate_run_identity_structure(run_identity)
            _validate_run_identity_match(shard_data, run_identity)
        except (ValueError, json.JSONDecodeError) as e:
            sys.stderr.write(f"{e}\n")
            sys.exit(1)

    shard_def_bytes = shard_def_path.read_bytes()
    shard_definition_sha256 = hashlib.sha256(shard_def_bytes).hexdigest()

    shard_id = shard_data["shard_id"]
    node_ids = shard_data["node_ids"]

    os.environ["KATTAPPA_TEST_MODE"] = "true"
    os.environ["KATTAPPA_SHARD_ID"] = shard_id
    os.environ["KATTAPPA_RUN_ID"] = shard_data.get("run_id", "")
    os.environ["KATTAPPA_CANDIDATE_COMMIT"] = shard_data.get("candidate_commit", "")

    shard_dir = shard_def_path.parent
    node_ids_file = shard_dir / "expected-node-ids.json"

    if node_ids_file.exists():
        node_ids_file.unlink()

    node_ids_tmp = node_ids_file.with_suffix(".json.tmp")
    node_ids_content = json.dumps(node_ids, indent=2)
    with open(node_ids_tmp, "w", encoding="utf-8") as f:
        f.write(node_ids_content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(node_ids_tmp, node_ids_file)

    reopened = json.loads(node_ids_file.read_text(encoding="utf-8"))
    if reopened != node_ids:
        sys.stderr.write("expected-node-ids.json content mismatch after write\n")
        sys.exit(1)

    expected_node_ids_sha256 = hashlib.sha256(
        node_ids_file.read_bytes()
    ).hexdigest()

    os.environ["KATTAPPA_SHARD_NODE_IDS_FILE"] = str(node_ids_file)

    unique_files = sorted(list(set(node.split("::")[0] for node in node_ids)))

    pytest_args = [
        "-o", "testpaths=",
        "-p", "no:cacheprovider",
        "-s",
        "-v"
    ] + unique_files

    plugin = KattappaResultPlugin(output_file=result_file_path)

    exit_code = int(pytest.main(pytest_args, plugins=[plugin]))

    # FAIL-CLOSED: Inject identity and hash fields into the result file
    if not result_file_path.exists():
        sys.stderr.write(
            f"SHARD_RESULT_IDENTITY_INJECTION_FAILED: Result file {result_file_path} was not created by pytest\n"
        )
        sys.exit(1)

    try:
        result_data = json.loads(result_file_path.read_text(encoding="utf-8"))
        for field in IDENTITY_FIELDS:
            result_data[field] = shard_data[field]
        result_data["shard_id"] = shard_id
        result_data["shard_definition_sha256"] = shard_definition_sha256
        result_data["expected_node_ids_sha256"] = expected_node_ids_sha256

        # Atomically overwrite result file
        tmp_result = result_file_path.with_suffix(".json.tmp")
        with open(tmp_result, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_result, result_file_path)

        # Verify atomic write
        verified_data = json.loads(result_file_path.read_text(encoding="utf-8"))
        assert verified_data.get("shard_definition_sha256") == shard_definition_sha256
        assert verified_data.get("expected_node_ids_sha256") == expected_node_ids_sha256
    except Exception as e:
        sys.stderr.write(f"SHARD_RESULT_IDENTITY_INJECTION_FAILED: Failed to inject identity into result: {e}\n")
        sys.exit(1)

    # FAIL-CLOSED: Require exact collection-set equality before execution success
    try:
        final_result_data = json.loads(result_file_path.read_text(encoding="utf-8"))
        if final_result_data.get("collection_set_match") is False:
            sys.stderr.write("SHARD_COLLECTION_SET_MISMATCH: collection_set_match is false in result file\n")
            if exit_code == 0:
                exit_code = 1
    except Exception as e:
        sys.stderr.write(f"SHARD_RESULT_VERIFICATION_FAILED: Cannot verify final result file: {e}\n")
        sys.exit(1)

    sys.stdout.flush()
    sys.stderr.flush()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
