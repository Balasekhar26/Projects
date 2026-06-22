"""Sandbox Improvement Lab (Step 6.5).

Implements Experiment Risk Classifier, Experiment Package Builder, Environment
Manager, Trace Replay Engine, Safety Auditor, Artifact Store, and Result Packager.
"""

from __future__ import annotations

import builtins
import json
import math
import socket
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from backend.core.config import runtime_data_root
from backend.core.proposal_governance import ProtectedCoreRegistry


class RiskLevel(str, Enum):
    R0 = "R0"  # Documentation only (minimal risk)
    R1 = "R1"  # Local behavior change (low risk)
    R2 = "R2"  # Architecture modification (medium risk)
    R3 = "R3"  # Critical system modification (high risk)
    R4 = "R4"  # Protected Core (forbidden, auto-reject)


@dataclass(frozen=True)
class ExperimentPackage:
    proposal_id: str
    parent_proposal_id: str | None
    risk_class: RiskLevel
    expected_gain: float
    expected_risk: float  # Predicted risk probability [0.0, 1.0]
    benchmark_targets: list[str]
    rollback_targets: list[str]
    created_at: float


def _experiments_store_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "experiments_store.json"


# -- 1. Experiment Risk Classifier -------------------------------------------
class ExperimentRiskClassifier:
    @classmethod
    def classify(cls, title: str, proposal: str, affected_modules: list[str]) -> RiskLevel:
        """Classifies the proposal risk level from R0 to R4."""
        # 1. Protected Core check yields R4
        if ProtectedCoreRegistry.check_affected_modules(affected_modules):
            return RiskLevel.R4

        text = f"{title} {proposal}".lower()
        for core_module in ProtectedCoreRegistry.PROTECTED_MODULES:
            if core_module in text or core_module.replace("_", " ") in text or core_module.replace("_", "") in text:
                return RiskLevel.R4

        # 2. Critical system modification yields R3
        r3_keywords = {"security", "policy", "reliability", "benchmark", "governance", "canary", "rollback"}
        for kw in r3_keywords:
            if kw in text:
                return RiskLevel.R3

        # 3. Architecture modification yields R2
        r2_keywords = {"validator", "planner", "consensus", "graph", "db schema", "restructure"}
        for kw in r2_keywords:
            if kw in text:
                return RiskLevel.R2

        # 4. Local behavior changes yields R1
        r1_keywords = {"tweak", "threshold", "retrieval", "cache", "index"}
        for kw in r1_keywords:
            if kw in text:
                return RiskLevel.R1

        # 5. Documentation or prompt edits yields R0
        r0_keywords = {"format", "prompt", "explanation", "docstring", "comment", "documentation"}
        for kw in r0_keywords:
            if kw in text:
                return RiskLevel.R0

        return RiskLevel.R1


# -- 2. Environment Manager (Ephemeral Sandbox Context) ----------------------
class EphemeralSandboxContext:
    def __enter__(self):
        import os
        import subprocess

        # 1. Block sockets and DNS lookups
        self._original_socket = socket.socket
        self._original_getaddrinfo = socket.getaddrinfo
        self._original_gethostbyname = socket.gethostbyname
        self._original_gethostbyname_ex = socket.gethostbyname_ex
        self._original_getnameinfo = socket.getnameinfo
        self._original_getfqdn = socket.getfqdn
        self._original_gethostbyaddr = socket.gethostbyaddr

        def blocked_socket(*args, **kwargs):
            raise RuntimeError("Outbound network access is disabled in the sandbox environment.")

        def blocked_dns(*args, **kwargs):
            raise RuntimeError("DNS lookups are disabled in the sandbox environment.")

        socket.socket = blocked_socket
        socket.getaddrinfo = blocked_dns
        socket.gethostbyname = blocked_dns
        socket.gethostbyname_ex = blocked_dns
        socket.getnameinfo = blocked_dns
        socket.getfqdn = blocked_dns
        socket.gethostbyaddr = blocked_dns

        # 2. Block file write operations
        self._original_open = builtins.open

        def blocked_open(file, mode="r", *args, **kwargs):
            if any(char in mode for char in ("w", "a", "x", "+")):
                raise IOError(f"Write operations are blocked for mode '{mode}' in the sandbox environment.")
            return self._original_open(file, mode, *args, **kwargs)

        builtins.open = blocked_open

        # 3. Block subprocess spawning and exec binary runs
        self._original_popen = subprocess.Popen
        self._original_system = os.system
        self._original_fork = getattr(os, "fork", None)
        self._original_execv = os.execv
        self._original_execve = os.execve
        self._original_posix_spawn = getattr(os, "posix_spawn", None)
        self._original_posix_spawnp = getattr(os, "posix_spawnp", None)
        self._original_spawnv = getattr(os, "spawnv", None)
        self._original_spawnve = getattr(os, "spawnve", None)

        def blocked_subprocess(*args, **kwargs):
            raise RuntimeError("Subprocess spawning is disabled in the sandbox environment.")

        subprocess.Popen = blocked_subprocess
        os.system = blocked_subprocess
        if hasattr(os, "fork"):
            os.fork = blocked_subprocess
        os.execv = blocked_subprocess
        os.execve = blocked_subprocess
        if hasattr(os, "posix_spawn"):
            os.posix_spawn = blocked_subprocess
        if hasattr(os, "posix_spawnp"):
            os.posix_spawnp = blocked_subprocess
        if hasattr(os, "spawnv"):
            os.spawnv = blocked_subprocess
        if hasattr(os, "spawnve"):
            os.spawnve = blocked_subprocess

        # 4. Strip environment credentials/secrets
        self._original_environ = dict(os.environ)
        self._deleted_environ = {}
        secret_patterns = ["key", "secret", "password", "token", "auth", "credential", "pwd", "private"]
        for k in list(os.environ.keys()):
            if any(pat in k.lower() for pat in secret_patterns):
                self._deleted_environ[k] = os.environ[k]
                del os.environ[k]

        self._original_environb = None
        self._deleted_environb = {}
        if hasattr(os, "environb"):
            self._original_environb = dict(os.environb)
            for k in list(os.environb.keys()):
                k_str = k.decode("utf-8", errors="ignore").lower()
                if any(pat in k_str for pat in secret_patterns):
                    self._deleted_environb[k] = os.environb[k]
                    del os.environb[k]

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import os
        import subprocess

        # Restore socket and DNS
        socket.socket = self._original_socket
        socket.getaddrinfo = self._original_getaddrinfo
        socket.gethostbyname = self._original_gethostbyname
        socket.gethostbyname_ex = self._original_gethostbyname_ex
        socket.getnameinfo = self._original_getnameinfo
        socket.getfqdn = self._original_getfqdn
        socket.gethostbyaddr = self._original_gethostbyaddr

        # Restore open
        builtins.open = self._original_open

        # Restore subprocess
        subprocess.Popen = self._original_popen
        os.system = self._original_system
        if self._original_fork is not None:
            os.fork = self._original_fork
        os.execv = self._original_execv
        os.execve = self._original_execve
        if self._original_posix_spawn is not None:
            os.posix_spawn = self._original_posix_spawn
        if self._original_posix_spawnp is not None:
            os.posix_spawnp = self._original_posix_spawnp
        if self._original_spawnv is not None:
            os.spawnv = self._original_spawnv
        if self._original_spawnve is not None:
            os.spawnve = self._original_spawnve

        # Restore environment
        for k, v in self._deleted_environ.items():
            os.environ[k] = v
        if self._deleted_environb and hasattr(os, "environb"):
            for kb, vb in self._deleted_environb.items():
                os.environb[kb] = vb


def _run_trace_in_process(mock_func: Callable[[dict[str, Any]], dict[str, Any]], trace: dict[str, Any], queue: Any) -> None:
    import resource
    # Set virtual memory limit to 256MB
    try:
        mem_limit = 256 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
    except Exception:
        pass
    # Set CPU time limit to 5 seconds
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    except Exception:
        pass

    try:
        with EphemeralSandboxContext():
            outcome = mock_func(trace)
        queue.put({"success": True, "outcome": outcome, "error": None})
    except Exception as e:
        queue.put({"success": False, "outcome": None, "error": str(e)})


# -- 3. Replay Engine --------------------------------------------------------
class ReplayEngine:
    DEFAULT_TRACES = [
        {"request_id": "req-1", "prompt": "Translate this user guide to German"},
        {"request_id": "req-2", "prompt": "Identify performance bottlenecks in the router lookup"},
        {"request_id": "req-3", "prompt": "List all active capability endpoints"},
        {"request_id": "req-4", "prompt": "Retrieve semantic database schema version"},
        {"request_id": "req-5", "prompt": "Format the response metadata output as clean markdown"},
    ]

    @classmethod
    def replay_traces(cls, mock_func: Callable[[dict[str, Any]], dict[str, Any]]) -> list[dict[str, Any]]:
        """Replays trace requests through the sandbox context and registers results."""
        import multiprocessing
        results = []
        for trace in cls.DEFAULT_TRACES:
            start_time = time.time()
            try:
                try:
                    ctx = multiprocessing.get_context("fork")
                    queue = ctx.Queue()
                    p = ctx.Process(target=_run_trace_in_process, args=(mock_func, trace, queue))
                    p.start()
                    p.join(timeout=5)
                    
                    if p.is_alive():
                        p.terminate()
                        p.join()
                        raise RuntimeError("Sandbox execution timed out (exceeded resource limits).")
                    
                    if queue.empty():
                        raise RuntimeError("Sandbox process exited unexpectedly without returning results.")
                    
                    outcome_wrapper = queue.get()
                    if outcome_wrapper["success"]:
                        outcome = outcome_wrapper["outcome"] or {}
                        latency = time.time() - start_time
                        results.append({
                            "request_id": trace["request_id"],
                            "success": outcome.get("success", True),
                            "latency_ms": round(latency * 1000, 2),
                            "error": None
                        })
                    else:
                        raise RuntimeError(outcome_wrapper["error"])
                except Exception as proc_exc:
                    # Fallback to in-process sandbox context if process spawning is blocked/fails
                    # But if the execution itself failed inside the process, re-raise the error.
                    if "process exited unexpectedly" in str(proc_exc) or "timed out" in str(proc_exc):
                        raise proc_exc
                    if not (isinstance(proc_exc, (ImportError, AttributeError, ValueError)) or "context" in str(proc_exc)):
                        # If the traceback wrapper failed due to mock_func raising an error, do not retry in-process
                        raise proc_exc
                    
                    with EphemeralSandboxContext():
                        outcome = mock_func(trace)
                    latency = time.time() - start_time
                    results.append({
                        "request_id": trace["request_id"],
                        "success": outcome.get("success", True),
                        "latency_ms": round(latency * 1000, 2),
                        "error": None
                    })
            except Exception as e:
                latency = time.time() - start_time
                results.append({
                    "request_id": trace["request_id"],
                    "success": False,
                    "latency_ms": round(latency * 1000, 2),
                    "error": str(e)
                })
        return results


# -- 4. Safety Auditor -------------------------------------------------------
class SafetyAuditor:
    @classmethod
    def audit_execution(cls, proposal_text: str, replay_results: list[dict[str, Any]]) -> tuple[bool, str]:
        """Audits sandbox execution outcomes and proposal text for safety violations."""
        text_lower = proposal_text.lower()
        
        # Check text checks
        safety_violations = {
            "bypass validator", "disable policy", "leak credentials", "fetch secrets",
            "rm -rf", "delete database", "drop table"
        }
        for violation in safety_violations:
            if violation in text_lower:
                return False, f"Safety violation detected in proposal text: '{violation}'"

        # Check execution errors
        for res in replay_results:
            err = res.get("error")
            if err:
                if "Outbound network access" in err:
                    return False, f"Security violation: Outbound network attempt blocked."
                if "Write operations are blocked" in err:
                    return False, f"Security violation: Unauthorized file mutation attempt blocked."
                if "DNS lookups are disabled" in err:
                    return False, f"Security violation: DNS lookup attempt blocked."
                if "Subprocess spawning is disabled" in err:
                    return False, f"Security violation: Subprocess spawning attempt blocked."

        return True, ""


# -- 5. Artifact Store -------------------------------------------------------
class ArtifactStore:
    @classmethod
    def save_experiment(cls, package: ExperimentPackage, results: dict[str, Any]) -> None:
        """Appends experiment result package to the database. Never overwrites."""
        path = _experiments_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        history = []
        if path.exists():
            try:
                history = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = []
            except Exception:
                pass

        history.append({
            "experiment_id": f"exp_{int(time.time())}_{package.proposal_id}",
            "package": asdict(package),
            "results": results,
            "recorded_at": time.time(),
        })
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    @classmethod
    def load_experiments(cls) -> list[dict[str, Any]]:
        """Loads all logged experiments."""
        path = _experiments_store_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


# -- 6. Result Packager & PRS Score -------------------------------------------
class ResultPackager:
    @classmethod
    def package_report(
        cls,
        package: ExperimentPackage,
        replay_results: list[dict[str, Any]],
        safety_success: bool,
        safety_message: str,
        actual_gain: float,
    ) -> dict[str, Any]:
        """Packages results and calculates metrics including the Prediction Reliability Score (PRS)."""
        # Calculate failure (safety failure = 1, success = 0)
        actual_risk = 1.0 if not safety_success else 0.0
        
        # Calculate PRS (Brier Risk Score)
        # Brier = (expected_risk - actual_risk)^2
        # PRS = 1.0 - Brier (higher is better)
        brier = (package.expected_risk - actual_risk) ** 2
        prs = 1.0 - brier

        # Evaluate passes
        success_count = sum(1 for r in replay_results if r.get("success"))
        replay_success = (success_count / len(replay_results)) >= 0.80 if replay_results else False

        recommendation = "PASS"
        if not safety_success or not replay_success:
            recommendation = "FAIL"
        elif actual_gain < package.expected_gain * 0.50:
            recommendation = "REVIEW"

        report = {
            "proposal_id": package.proposal_id,
            "risk_class": package.risk_class.value,
            "expected_gain": package.expected_gain,
            "actual_gain": actual_gain,
            "expected_risk": package.expected_risk,
            "actual_risk": actual_risk,
            "brier_risk_score": round(brier, 4),
            "prs_score": round(prs, 4),
            "replay_success_rate": success_count / len(replay_results) if replay_results else 0.0,
            "safety_passed": safety_success,
            "safety_message": safety_message,
            "recommendation": recommendation,
            "timestamp": time.time(),
        }

        # Save to Artifact Store
        ArtifactStore.save_experiment(package, report)
        return report

    @classmethod
    def get_overall_prs(cls) -> float:
        """Calculates cumulative PRS across all run experiments."""
        experiments = ArtifactStore.load_experiments()
        if not experiments:
            return 1.0
        
        brier_sum = 0.0
        count = 0
        for exp in experiments:
            res = exp.get("results", {})
            if "brier_risk_score" in res:
                brier_sum += res["brier_risk_score"]
                count += 1

        if count == 0:
            return 1.0
        mean_brier = brier_sum / count
        return round(1.0 - mean_brier, 4)
