from __future__ import annotations

from .config import ASAConfig
from .logging_engine import JsonlLogger
from .models import ActionResult, ThreatFinding
from .self_healing import SelfHealingEngine


class ResponseEngine:
    def __init__(self, config: ASAConfig, logger: JsonlLogger) -> None:
        self.config = config
        self.logger = logger
        self.self_healing = SelfHealingEngine(config)

    def respond(self, findings: list[ThreatFinding]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for finding in findings:
            result = self._respond_to_finding(finding)
            if result is not None:
                self.logger.action(result)
                results.append(result)
        return results

    def _respond_to_finding(self, finding: ThreatFinding) -> ActionResult | None:
        if not self.config.response.auto_contain:
            return ActionResult(
                "recommend_action",
                True,
                "Auto-containment disabled; finding logged for review",
                {
                    "kind": finding.kind,
                    "score": finding.score,
                    "recommended": finding.reversible_action,
                },
            )

        if finding.score >= self.config.response.kill_threshold:
            pid = finding.evidence.get("pid")
            if isinstance(pid, int):
                return self.self_healing.terminate_process(
                    pid,
                    dry_run=self.config.response.dry_run,
                )

        if finding.score >= self.config.response.block_threshold:
            remote_ip = finding.evidence.get("remote_ip")
            if isinstance(remote_ip, str) and remote_ip:
                return self.local_block_ip(remote_ip)

        return None

    def local_block_ip(self, ip: str) -> ActionResult:
        self.config.ensure_dirs()
        existing = {
            line.strip()
            for line in self.config.blocklist_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if ip not in existing:
            with self.config.blocklist_file.open("a", encoding="utf-8") as handle:
                handle.write(ip + "\n")
        return ActionResult(
            "local_block_ip",
            True,
            "IP added to local blocklist for future alerts",
            {"ip": ip},
        )

