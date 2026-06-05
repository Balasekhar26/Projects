from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from .config import ASAConfig, load_config
from .hardening import HardeningLayer
from .learning import BaselineStore
from .logging_engine import JsonlLogger
from .models import ActionResult, SystemMap, ThreatFinding
from .reporting import ReportWriter
from .response import ResponseEngine
from .system_map import SystemMapper
from .threat_detection import ThreatDetectionEngine

T = TypeVar("T")


@dataclass
class PipelineReport:
    system_counts: dict[str, int] = field(default_factory=dict)
    findings: list[ThreatFinding] = field(default_factory=list)
    actions: list[ActionResult] = field(default_factory=list)
    hardening: list[ActionResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    baseline_saved: bool = False
    report_path: str = ""
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "system_counts": self.system_counts,
            "findings": [vars(item) for item in self.findings],
            "actions": [vars(item) for item in self.actions],
            "hardening": [vars(item) for item in self.hardening],
            "errors": self.errors,
            "baseline_saved": self.baseline_saved,
            "report_path": self.report_path,
        }


def run_pipeline(
    config: ASAConfig | None = None,
    *,
    save_baseline: bool = False,
    write_report: bool = False,
) -> PipelineReport:
    """Run the ASA layers as one defensive workflow.

    Each layer appends to the same report object. A layer failure is recorded and
    logged, but later layers still run when their inputs are available.
    """

    config = config or load_config()
    config.ensure_dirs()
    logger = JsonlLogger(config)
    baseline = BaselineStore(config)
    report = PipelineReport()

    logger.event("info", "pipeline", "pipeline_started", "ASA pipeline started")

    def step(name: str, func: Callable[[], T]) -> T | None:
        try:
            return func()
        except Exception as exc:  # pragma: no cover - defensive boundary
            report.errors.append({"layer": name, "error": str(exc)})
            logger.event("warning", "pipeline", f"{name}_failed", str(exc))
            return None

    system_map = step("layer1_scan", lambda: SystemMapper(config).build())
    if system_map is None:
        system_map = SystemMap()
    report.system_counts = {
        "processes": len(system_map.processes),
        "network_connections": len(system_map.network_connections),
        "startup_entries": len(system_map.startup_entries),
        "file_observations": len(system_map.file_observations),
    }

    findings = step(
        "layer2_detect",
        lambda: ThreatDetectionEngine(config, baseline).analyze(system_map),
    )
    report.findings = findings or []
    for finding in report.findings:
        logger.finding(finding)

    actions = step(
        "layer3_selfheal_layer6_respond",
        lambda: ResponseEngine(config, logger).respond(report.findings),
    )
    report.actions = actions or []

    hardening = step("layer4_harden", lambda: HardeningLayer(config).audit())
    report.hardening = hardening or []
    for result in report.hardening:
        logger.action(result)

    if save_baseline:
        saved = step("layer7_learn", lambda: baseline.save(system_map))
        report.baseline_saved = saved is not None

    if write_report:
        path = step("report", lambda: ReportWriter(config).write())
        report.report_path = str(path) if path is not None else ""

    report.severity = _severity(report.findings, report.errors)
    logger.event(
        "info",
        "pipeline",
        "pipeline_finished",
        "ASA pipeline finished",
        severity=report.severity,
        findings=len(report.findings),
        actions=len(report.actions),
        hardening=len(report.hardening),
        errors=len(report.errors),
    )
    return report


def _severity(findings: list[ThreatFinding], errors: list[dict[str, str]]) -> str:
    if any(item.level == "critical" or item.score >= 90 for item in findings):
        return "critical"
    if any(item.score >= 70 for item in findings) or errors:
        return "warning"
    if findings:
        return "notice"
    return "info"
