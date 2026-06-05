from __future__ import annotations

import time

from .config import ASAConfig
from .learning import BaselineStore
from .logging_engine import JsonlLogger
from .response import ResponseEngine
from .system_map import SystemMapper
from .threat_detection import ThreatDetectionEngine


class MonitoringLoop:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config
        self.logger = JsonlLogger(config)
        self.baseline = BaselineStore(config)
        self.mapper = SystemMapper(config)
        self.detector = ThreatDetectionEngine(config, self.baseline)
        self.response = ResponseEngine(config, self.logger)

    def scan_once(self) -> int:
        self.logger.event("info", "monitoring", "scan_started", "ASA scan started")
        system_map = self.mapper.build()
        findings = self.detector.analyze(system_map)
        for finding in findings:
            self.logger.finding(finding)
        self.response.respond(findings)
        self.logger.event(
            "info",
            "monitoring",
            "scan_finished",
            "ASA scan finished",
            findings=len(findings),
        )
        return len(findings)

    def watch(self, interval_seconds: int | None = None) -> None:
        interval = interval_seconds or self.config.scan_interval_seconds
        self.logger.event(
            "info",
            "monitoring",
            "watch_started",
            "ASA watch loop started",
            interval_seconds=interval,
        )
        while True:
            self.scan_once()
            time.sleep(interval)

