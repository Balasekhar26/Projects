from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResponsePolicy:
    auto_contain: bool = False
    kill_threshold: int = 90
    block_threshold: int = 80
    dry_run: bool = True


@dataclass(frozen=True)
class ASAConfig:
    root: Path
    runtime_dir: Path
    reports_dir: Path
    policy_file: Path
    scan_interval_seconds: int = 15
    max_cpu_percent: float = 80.0
    max_memory_percent: float = 70.0
    max_connections_per_process: int = 30
    suspicious_remote_ports: set[int] = field(default_factory=set)
    suspicious_process_patterns: tuple[str, ...] = ()
    risky_process_paths: tuple[Path, ...] = ()
    protected_process_names: set[str] = field(default_factory=set)
    critical_file_paths: tuple[Path, ...] = ()
    response: ResponsePolicy = field(default_factory=ResponsePolicy)
    nvidia_enabled: bool = False
    nvidia_api_key_env: str = "NVIDIA_NIM_API_KEY"
    nvidia_base_url: str = "https://integrate.api.nvidia.com"
    nvidia_model: str = "nvidia/llama-3.1-nemotron-nano-4b-v1_1"
    nvidia_timeout_seconds: int = 60
    nvidia_max_tokens: int = 900

    @property
    def log_dir(self) -> Path:
        return self.runtime_dir / "logs"

    @property
    def evidence_dir(self) -> Path:
        return self.runtime_dir / "evidence"

    @property
    def honeypot_dir(self) -> Path:
        return self.runtime_dir / "honeypot"

    @property
    def quarantine_dir(self) -> Path:
        return self.runtime_dir / "quarantine"

    @property
    def event_log(self) -> Path:
        return self.log_dir / "asa-events.jsonl"

    @property
    def blocklist_file(self) -> Path:
        return self.runtime_dir / "blocklist.txt"

    @property
    def baseline_file(self) -> Path:
        return self.runtime_dir / "baseline.json"

    def ensure_dirs(self) -> None:
        for path in (
            self.log_dir,
            self.evidence_dir,
            self.honeypot_dir,
            self.quarantine_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.blocklist_file.touch(exist_ok=True)


def _expand_paths(values: list[str], root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for value in values:
        expanded = Path(value).expanduser()
        if not expanded.is_absolute():
            expanded = root / expanded
        paths.append(expanded)
    return tuple(paths)


def load_config(root: Path | None = None, policy_file: Path | None = None) -> ASAConfig:
    project_root = root or Path(__file__).resolve().parents[1]
    policy_path = policy_file or project_root / "config" / "asa-policy.json"
    raw: dict[str, Any] = {}
    if policy_path.exists():
        raw = json.loads(policy_path.read_text(encoding="utf-8"))

    response_raw = raw.get("response", {})
    nvidia_raw = raw.get("nvidia", {})
    response = ResponsePolicy(
        auto_contain=bool(response_raw.get("auto_contain", False)),
        kill_threshold=int(response_raw.get("kill_threshold", 90)),
        block_threshold=int(response_raw.get("block_threshold", 80)),
        dry_run=bool(response_raw.get("dry_run", True)),
    )

    return ASAConfig(
        root=project_root,
        runtime_dir=project_root / "runtime",
        reports_dir=project_root / "reports",
        policy_file=policy_path,
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 15)),
        max_cpu_percent=float(raw.get("max_cpu_percent", 80.0)),
        max_memory_percent=float(raw.get("max_memory_percent", 70.0)),
        max_connections_per_process=int(raw.get("max_connections_per_process", 30)),
        suspicious_remote_ports={int(p) for p in raw.get("suspicious_remote_ports", [])},
        suspicious_process_patterns=tuple(
            str(p).lower() for p in raw.get("suspicious_process_patterns", [])
        ),
        risky_process_paths=_expand_paths(raw.get("risky_process_paths", []), project_root),
        protected_process_names={str(p) for p in raw.get("protected_process_names", [])},
        critical_file_paths=_expand_paths(raw.get("critical_file_paths", []), project_root),
        response=response,
        nvidia_enabled=bool(nvidia_raw.get("enabled", False)),
        nvidia_api_key_env=str(nvidia_raw.get("api_key_env", "NVIDIA_NIM_API_KEY")),
        nvidia_base_url=str(nvidia_raw.get("base_url", "https://integrate.api.nvidia.com")),
        nvidia_model=str(
            nvidia_raw.get("model", "nvidia/llama-3.1-nemotron-nano-4b-v1_1")
        ),
        nvidia_timeout_seconds=int(nvidia_raw.get("timeout_seconds", 60)),
        nvidia_max_tokens=int(nvidia_raw.get("max_tokens", 900)),
    )
