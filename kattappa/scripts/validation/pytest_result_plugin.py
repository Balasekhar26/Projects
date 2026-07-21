import json
import sys
import pytest
from pathlib import Path

class KattappaResultPlugin:
    def __init__(self, output_file: Path):
        self.output_file = output_file
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

    def pytest_collection_finish(self, session):
        for item in session.items:
            self.collected_node_ids.add(item.nodeid)

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

    def pytest_internalerror(self, excreport, excinfo):
        self.internal_errors.append({
            "type": excinfo.typename,
            "message": str(excinfo.value),
            "repr": str(excreport)
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
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_file.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

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
