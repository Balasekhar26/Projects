import json
import sys
import os
import re
import hashlib
import pytest
from pathlib import Path


class KattappaResultPlugin:
    def __init__(self, output_file: Path):
        self.output_file = Path(output_file) if not isinstance(output_file, Path) else output_file
        self.expected_node_ids = None  # Set after loading from file
        self.collected_node_ids = set()
        self.attempted_node_ids = set()
        self.call_executed_node_ids = set()
        self.completed_node_ids = set()

        self.outcomes = {
            "passed": [],
            "failed": [],
            "errors": [],
            "skipped": [],
            "xfailed": [],
            "xpassed": []
        }
        self.internal_errors = []
        self.collection_errors = []
        self.collection_set_match = None
        self.missing_expected_node_ids = []
        self.unexpected_collected_node_ids = []

    def pytest_collection_modifyitems(self, config, items):
        node_ids_file = os.environ.get("KATTAPPA_SHARD_NODE_IDS_FILE")
        if not node_ids_file:
            # No node file specified — no filtering requested
            return

        node_ids_path = Path(node_ids_file)

        # Fail-closed: missing file
        if not node_ids_path.exists():
            raise pytest.UsageError(
                f"SHARD_NODE_FILTER_FAIL_CLOSED: Node IDs file not found: {node_ids_file}"
            )

        # Fail-closed: unreadable file
        try:
            raw = node_ids_path.read_text(encoding="utf-8")
        except Exception as e:
            raise pytest.UsageError(
                f"SHARD_NODE_FILTER_FAIL_CLOSED: Cannot read node IDs file: {e}"
            )

        # Fail-closed: invalid JSON
        try:
            allowed_nodes_list = json.loads(raw)
        except json.JSONDecodeError as e:
            raise pytest.UsageError(
                f"SHARD_NODE_FILTER_FAIL_CLOSED: Invalid JSON in node IDs file: {e}"
            )

        # Fail-closed: not a list
        if not isinstance(allowed_nodes_list, list):
            raise pytest.UsageError(
                f"SHARD_NODE_FILTER_FAIL_CLOSED: Node IDs file must contain a JSON list, got {type(allowed_nodes_list).__name__}"
            )

        # Fail-closed: empty unexpectedly
        if len(allowed_nodes_list) == 0:
            raise pytest.UsageError(
                "SHARD_NODE_FILTER_FAIL_CLOSED: Node IDs list is empty"
            )

        # Fail-closed: duplicate node IDs
        if len(allowed_nodes_list) != len(set(allowed_nodes_list)):
            from collections import Counter
            dupes = [k for k, v in Counter(allowed_nodes_list).items() if v > 1]
            raise pytest.UsageError(
                f"SHARD_NODE_FILTER_FAIL_CLOSED: Duplicate node IDs found: {dupes[:5]}"
            )

        allowed_nodes = set(allowed_nodes_list)

        # Build normalized lookup sets for flexible path matching (handles rootdir shifts)
        allowed_nodes_norm = {n.replace("\\", "/").strip() for n in allowed_nodes}

        def _item_matches(item) -> bool:
            # 1. Direct exact match
            if item.nodeid in allowed_nodes:
                return True
            # 2. Normalized slash match
            norm_nodeid = item.nodeid.replace("\\", "/").strip()
            if norm_nodeid in allowed_nodes_norm:
                return True
            # 3. Absolute path match (when pytest rootdir shifts to tempdir)
            try:
                abs_file = str(Path(item.path).resolve()).replace("\\", "/")
                func_part = item.nodeid.split("::", 1)[1] if "::" in item.nodeid else item.name
                abs_node = f"{abs_file}::{func_part}"
                if abs_node in allowed_nodes_norm:
                    return True
            except Exception:
                pass
            return False

        self.expected_node_ids = allowed_nodes.copy()

        kept = []
        for item in items:
            if _item_matches(item):
                kept.append(item)
        items[:] = kept

    def pytest_collection_finish(self, session):
        for item in session.items:
            self.collected_node_ids.add(item.nodeid)

        # Exact collection-set verification (only when filtering was requested)
        if self.expected_node_ids is not None:
            expected = self.expected_node_ids

            def _norm(nid: str) -> str:
                return nid.replace("\\", "/").strip()

            expected_norm_map = {_norm(n): n for n in expected}
            collected_norm = {_norm(c) for c in self.collected_node_ids}
            for item in session.items:
                try:
                    abs_file = str(Path(item.path).resolve()).replace("\\", "/")
                    func_part = item.nodeid.split("::", 1)[1] if "::" in item.nodeid else item.name
                    collected_norm.add(f"{abs_file}::{func_part}")
                except Exception:
                    pass

            missing_norm = set(expected_norm_map.keys()) - collected_norm
            self.missing_expected_node_ids = sorted([expected_norm_map[k] for k in missing_norm])

            expected_norm = set(expected_norm_map.keys())
            unexpected_norm = {c for c in self.collected_node_ids if _norm(c) not in expected_norm}
            self.unexpected_collected_node_ids = sorted(list(unexpected_norm))

            self.collection_set_match = (
                len(self.missing_expected_node_ids) == 0
                and len(self.unexpected_collected_node_ids) == 0
            )

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append({
                "nodeid": getattr(report, "nodeid", "unknown"),
                "longrepr": str(report.longrepr)
            })

    def pytest_runtest_logreport(self, report):
        nodeid = report.nodeid
        self.attempted_node_ids.add(nodeid)

        # Track call execution
        if report.when == "call":
            self.call_executed_node_ids.add(nodeid)

        # Teardown / final phase completed
        if report.when == "teardown" and not report.failed:
            self.completed_node_ids.add(nodeid)

        # Check xfail / wasxfail semantics
        was_xfail = hasattr(report, "wasxfail")

        if report.when == "setup":
            if report.failed:
                self.outcomes["errors"].append(nodeid)
            elif report.skipped:
                if was_xfail:
                    self.outcomes["xfailed"].append(nodeid)
                else:
                    self.outcomes["skipped"].append(nodeid)

        elif report.when == "call":
            if report.passed:
                if was_xfail:
                    self.outcomes["xpassed"].append(nodeid)
                else:
                    self.outcomes["passed"].append(nodeid)
            elif report.failed:
                if was_xfail:
                    self.outcomes["xfailed"].append(nodeid)
                else:
                    self.outcomes["failed"].append(nodeid)
            elif report.skipped:
                if was_xfail:
                    self.outcomes["xfailed"].append(nodeid)
                else:
                    self.outcomes["skipped"].append(nodeid)

        elif report.when == "teardown":
            if report.failed:
                # Teardown failure overrides prior call pass
                if nodeid in self.outcomes["passed"]:
                    self.outcomes["passed"].remove(nodeid)
                if nodeid not in self.outcomes["errors"]:
                    self.outcomes["errors"].append(nodeid)

    def pytest_internalerror(self, excrepr, excinfo):
        self.internal_errors.append({
            "type": "pytest_internalerror",
            "representation": str(excrepr),
            "exception": str(excinfo.value) if excinfo else None,
        })

    def pytest_sessionfinish(self, session, exitstatus):
        result_payload = {
            "collected_node_ids": sorted(list(self.collected_node_ids)),
            "attempted_node_ids": sorted(list(self.attempted_node_ids)),
            "executed_node_ids": sorted(list(self.call_executed_node_ids)),
            "completed_node_ids": sorted(list(self.completed_node_ids)),
            "passed": len(self.outcomes["passed"]),
            "failed": len(self.outcomes["failed"]),
            "errors": len(self.outcomes["errors"]),
            "skipped": len(self.outcomes["skipped"]),
            "xfailed": len(self.outcomes["xfailed"]),
            "xpassed": len(self.outcomes["xpassed"]),
            "outcomes": self.outcomes,
            "internal_errors": self.internal_errors,
            "collection_errors": self.collection_errors,
            "exit_status": exitstatus
        }

        # Add collection-set verification fields when filtering was active
        if self.expected_node_ids is not None:
            result_payload["expected_node_ids"] = sorted(list(self.expected_node_ids))
            result_payload["missing_expected_node_ids"] = self.missing_expected_node_ids
            result_payload["unexpected_collected_node_ids"] = self.unexpected_collected_node_ids
            result_payload["collection_set_match"] = self.collection_set_match

        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(result_payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

def pytest_configure(config):
    outfile = config.getoption("kattappa_result_file", None)
    if outfile:
        plugin = KattappaResultPlugin(Path(outfile))
        config.pluginmanager.register(plugin, "kattappa_result_plugin")

def pytest_addoption(parser):
    parser.addoption(
        "--kattappa-result-file",
        action="store",
        default=None,
        help="Path to save Kattappa machine-readable test execution results JSON"
    )
