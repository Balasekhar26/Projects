from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .architecture_audit import ArchitectureAudit
from .hardening import HardeningLayer
from .learning import BaselineStore
from .logging_engine import JsonlLogger
from .monitoring import MonitoringLoop
from .network_scan import scan_local_network
from .pipeline import run_pipeline
from .reporting import ReportWriter
from .response import ResponseEngine
from .self_healing import SelfHealingEngine
from .system_map import SystemMapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Balu Cyber Shield ASA engine")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("map", help="Print the current system map as JSON")
    subcommands.add_parser("scan", help="Run one ASA scan")
    pipeline = subcommands.add_parser("pipeline", help="Run all ASA layers as one workflow")
    pipeline.add_argument("--save-baseline", action="store_true", help="Save scan as baseline")
    pipeline.add_argument("--write-report", action="store_true", help="Write a markdown report")
    watch = subcommands.add_parser("watch", help="Run the ASA monitor loop")
    watch.add_argument("seconds", nargs="?", type=int)
    subcommands.add_parser("baseline", help="Save current system behavior baseline")
    subcommands.add_parser("hardening-audit", help="Run local hardening audit")
    subcommands.add_parser("architecture-audit", help="Check ASA architecture and safety boundaries")
    subcommands.add_parser("report", help="Generate ASA report")
    network_scan = subcommands.add_parser(
        "network-scan",
        help="Run a safe local/private TCP port scan with Nmap if installed or a socket fallback",
    )
    network_scan.add_argument("target", nargs="?", default="127.0.0.1")
    network_scan.add_argument(
        "--ports",
        default="",
        help="Comma-separated ports or small ranges, limited to 50 ports",
    )
    network_scan.add_argument("--no-nmap", action="store_true", help="Use the built-in socket fallback")

    contain = subcommands.add_parser("contain-pid", help="Safely contain a local process")
    contain.add_argument("pid", type=int)
    contain.add_argument("--apply", action="store_true", help="Actually send TERM")

    block_ip = subcommands.add_parser("block-ip", help="Add IP to local blocklist")
    block_ip.add_argument("ip")

    virus_scan = subcommands.add_parser("virus-scan", help="Run ClamAV or signature-matching directory scan")
    virus_scan.add_argument("directory", nargs="?", default=".")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config()
    config.ensure_dirs()
    logger = JsonlLogger(config)

    if args.command == "map":
        system_map = SystemMapper(config).build()
        print(json.dumps(system_map.to_dict(), indent=2, sort_keys=True, default=str))
        return 0

    if args.command == "scan":
        count = MonitoringLoop(config).scan_once()
        print(f"ASA scan complete. Findings: {count}")
        print(f"Log: {config.event_log}")
        return 0

    if args.command == "pipeline":
        result = run_pipeline(
            config,
            save_baseline=args.save_baseline,
            write_report=args.write_report,
        )
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
        return 1 if result.errors else 0

    if args.command == "watch":
        MonitoringLoop(config).watch(args.seconds)
        return 0

    if args.command == "baseline":
        system_map = SystemMapper(config).build()
        BaselineStore(config).save(system_map)
        logger.event("info", "learning", "baseline_saved", "System baseline saved")
        print(f"Baseline saved: {config.baseline_file}")
        return 0

    if args.command == "hardening-audit":
        results = HardeningLayer(config).audit()
        for result in results:
            logger.action(result)
            status = "OK" if result.ok else "REVIEW"
            print(f"{status}: {result.message} {result.evidence}")
        return 0

    if args.command == "architecture-audit":
        checks = ArchitectureAudit(config).run()
        failed = False
        for check in checks:
            status = "OK" if check.ok else "REVIEW"
            if not check.ok:
                failed = True
            print(f"{status}: {check.layer} :: {check.target} :: {check.message}")
        return 1 if failed else 0

    if args.command == "report":
        path = ReportWriter(config).write()
        logger.event("info", "report", "asa_report_created", "ASA report generated", path=str(path))
        print(path)
        return 0

    if args.command == "network-scan":
        try:
            result = scan_local_network(
                args.target,
                ports=args.ports,
                prefer_nmap=not args.no_nmap,
            )
        except ValueError as exc:
            print(f"Network scan blocked: {exc}")
            return 1
        logger.event(
            "info",
            "network_scan",
            "local_network_scan_complete",
            "Safe local/private network scan completed",
            engine=result["engine"],
            target=result["target"],
            open_ports=result["observations"],
        )
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0

    if args.command == "contain-pid":
        result = SelfHealingEngine(config).terminate_process(args.pid, dry_run=not args.apply)
        logger.action(result)
        print(result.message)
        return 0 if result.ok else 1

    if args.command == "block-ip":
        result = ResponseEngine(config, logger).local_block_ip(args.ip)
        logger.action(result)
        print(result.message)
        return 0

    if args.command == "virus-scan":
        from .clamav_driver import ClamAvScanner
        scanner = ClamAvScanner(config)
        try:
            result = scanner.scan_directory(args.directory)
            engine = result["engine"]
            findings = result["findings"]
            status = result["scan_status"]
            infected = result["infected_count"]

            logger.event(
                "info",
                "virus_scan",
                "directory_scan_complete",
                f"Virus scan of {args.directory} completed. Infected: {infected}",
                engine=engine,
                status=status,
                infected_count=infected
            )

            for finding in findings:
                logger.event(
                    "error" if finding["severity"] == "critical" else "warning",
                    "threat_detection",
                    "malware_signature_detected",
                    f"Detected malware signature '{finding['threat_name']}' in file {finding['file_path']}",
                    file_path=finding["file_path"],
                    threat_name=finding["threat_name"],
                    severity=finding["severity"]
                )

            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 0 if infected == 0 else 1
        except Exception as exc:
            print(f"Virus scan failed: {exc}")
            return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
