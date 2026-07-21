import json
import os
import pytest

class KattappaResultPlugin:
    def __init__(self, output_path: str):
        self.output_path = output_path
        self.collected_node_ids = []
        self.executed_node_ids = []
        self.outcomes = {
            "passed": [],
            "failed": [],
            "errors": [],
            "skipped": [],
            "xfailed": [],
            "xpassed": []
        }
        self.collection_errors = []
        self.internal_errors = []

    def pytest_collection_finish(self, session):
        self.collected_node_ids = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.nodeid not in self.executed_node_ids:
                self.executed_node_ids.append(report.nodeid)
            if report.passed:
                if hasattr(report, "wasxfail"):
                    self.outcomes["xpassed"].append(report.nodeid)
                else:
                    self.outcomes["passed"].append(report.nodeid)
            elif report.failed:
                if hasattr(report, "wasxfail"):
                    self.outcomes["xfailed"].append(report.nodeid)
                else:
                    self.outcomes["failed"].append(report.nodeid)
            elif report.skipped:
                self.outcomes["skipped"].append(report.nodeid)
        elif report.when in ("setup", "teardown") and report.failed:
            self.outcomes["errors"].append(f"{report.nodeid}::{report.when}")

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append(f"{report.nodeid}: {report.longrepr}")

    def pytest_sessionfinish(self, session, exitstatus):
        result = {
            "collected_node_ids": self.collected_node_ids,
            "executed_node_ids": self.executed_node_ids,
            "outcomes": self.outcomes,
            "collection_errors": self.collection_errors,
            "internal_errors": self.internal_errors,
            "exit_status": exitstatus
        }
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

def pytest_configure(config):
    output_path = os.getenv("KATTAPPA_RESULT_JSON")
    if output_path:
        plugin = KattappaResultPlugin(output_path)
        config.pluginmanager.register(plugin, "kattappa_result_plugin")
