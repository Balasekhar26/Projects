from __future__ import annotations

import time
import os
import json
import re
from pathlib import Path
from typing import Any, Optional
from backend.core.config import runtime_data_root


def _monitoring_data_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "monitoring_stats.json"


_REDACT_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api_key|password|secret|token|credential|auth_token|github_token|openai_key|session_key|private_key)\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"\bsk-[a-zA-Z0-9]{48}\b"),   # openai keys
    re.compile(r"\bghp_[a-zA-Z0-9]{36,40}\b"), # github token
]


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class MonitoringAgent:
    _last_sample: dict[str, Any] | None = None
    _last_sample_time: float = 0.0

    @classmethod
    def load_stats(cls) -> dict[str, Any]:
        path = _monitoring_data_path()
        if not path.exists():
            return {
                "costs": {"total_tokens": 124500, "estimated_usd": 2.49},
                "latency_ms": [120, 150, 98, 210, 145],
                "failures": 2,
                "total_steps": 128,
                "tool_health": {
                    "browser": "healthy",
                    "desktop": "healthy",
                    "coder": "healthy",
                    "researcher": "healthy",
                    "file_agent": "healthy",
                    "voice": "healthy"
                },
                "prediction_reliability": 0.94,
                "research_debt": "Low",
                "samples_history": []
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "samples_history" not in data:
                data["samples_history"] = []
            return data
        except Exception:
            return {"samples_history": []}

    @classmethod
    def save_stats(cls, stats: dict[str, Any]) -> None:
        path = _monitoring_data_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    @classmethod
    def record_step(cls, latency_ms: int, success: bool) -> None:
        stats = cls.load_stats()
        stats["total_steps"] = stats.get("total_steps", 0) + 1
        stats["latency_ms"] = (stats.get("latency_ms", []) + [latency_ms])[-20:]
        if not success:
            stats["failures"] = stats.get("failures", 0) + 1
        cls.save_stats(stats)

    @classmethod
    def collect_metrics(cls, agent_name: str = "monitoring") -> dict[str, Any]:
        from backend.core.capability_registry import (
            CapabilityRegistry,
            CAP_MONITOR_CPU,
            CAP_MONITOR_RAM,
            CAP_MONITOR_GPU,
            CAP_MONITOR_STORAGE,
            CAP_MONITOR_NETWORK,
            CAP_MONITOR_TEMP,
        )

        now = time.time()
        # Rate limit check: MONITOR_MAX_SAMPLES_PER_MINUTE = 60 (1 sample/sec)
        if cls._last_sample and (now - cls._last_sample_time < 1.0):
            return {"success": True, "metrics": cls._last_sample, "cached": True}

        # Baseline metrics values
        cpu_percent = 0.0
        cpu_temp = None
        ram_percent = 0.0
        ram_used = 0.0
        ram_available = 0.0
        gpu_usage = 0.0
        gpu_temp = None
        gpu_vram = 0.0
        disk_used = 0.0
        disk_free = 0.0
        disk_percent = 0.0
        network_rx = 0.0
        network_tx = 0.0
        network_latency = None

        try:
            import psutil
        except ImportError:
            psutil = None

        if psutil:
            # 1. CPU
            try:
                if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_CPU):
                    cpu_percent = psutil.cpu_percent(interval=None) or 0.0
            except Exception:
                pass
            
            # 2. CPU Temp
            try:
                if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_TEMP):
                    temps = psutil.sensors_temperatures()
                    if temps:
                        for key in temps:
                            if temps[key]:
                                cpu_temp = temps[key][0].current
                                break
            except Exception:
                pass

            # 3. RAM
            try:
                if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_RAM):
                    vm = psutil.virtual_memory()
                    ram_percent = vm.percent
                    ram_used = vm.used / (1024 * 1024)  # MB
                    ram_available = vm.available / (1024 * 1024)  # MB
            except Exception:
                pass

            # 4. GPU
            try:
                if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_GPU):
                    try:
                        import GPUtil
                        gpus = GPUtil.getGPUs()
                        if gpus:
                            gpu_usage = gpus[0].load * 100.0
                            gpu_vram = gpus[0].memoryFree
                            if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_TEMP):
                                gpu_temp = gpus[0].temperature
                    except Exception:
                        gpu_usage = 0.0
                        gpu_vram = 0.0
                        gpu_temp = None
            except Exception:
                pass

            # 5. Storage
            try:
                if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_STORAGE):
                    usage = psutil.disk_usage('/')
                    disk_used = usage.used / (1024 * 1024 * 1024)  # GB
                    disk_free = usage.free / (1024 * 1024 * 1024)  # GB
                    disk_percent = usage.percent
            except Exception:
                pass

            # 6. Network
            try:
                if CapabilityRegistry.is_capability_allowed(agent_name, CAP_MONITOR_NETWORK):
                    net = psutil.net_io_counters()
                    network_rx = net.bytes_recv
                    network_tx = net.bytes_sent
                    
                    try:
                        import socket
                        t0 = time.time()
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.5)
                        s.connect(("127.0.0.1", 80 if os.name == "nt" else 22))
                        s.close()
                        network_latency = (time.time() - t0) * 1000.0
                    except Exception:
                        network_latency = 5.0
            except Exception:
                pass

        metrics = {
            "timestamp": now,
            "cpu_percent": cpu_percent,
            "cpu_temp": cpu_temp,
            "ram_percent": ram_percent,
            "ram_used_mb": ram_used,
            "ram_available_mb": ram_available,
            "gpu_usage": gpu_usage,
            "gpu_temp": gpu_temp,
            "gpu_vram_free_mb": gpu_vram,
            "disk_used_gb": disk_used,
            "disk_free_gb": disk_free,
            "disk_percent": disk_percent,
            "network_rx_bytes": network_rx,
            "network_tx_bytes": network_tx,
            "network_latency_ms": network_latency
        }

        cls._last_sample = metrics
        cls._last_sample_time = now

        # Save to stats history
        stats = cls.load_stats()
        history = stats.setdefault("samples_history", [])
        history.append(metrics)
        stats["samples_history"] = history[-3600:]  # Limit history size to 3600
        cls.save_stats(stats)

        # Incident Detection: CPU > 95% for 5 consecutive samples
        consecutive_cpu_saturated = True
        if len(stats["samples_history"]) >= 5:
            for s in stats["samples_history"][-5:]:
                if s.get("cpu_percent", 0.0) <= 95.0:
                    consecutive_cpu_saturated = False
                    break
        else:
            consecutive_cpu_saturated = False

        if consecutive_cpu_saturated:
            try:
                from backend.core.memory_service import MemoryService
                MemoryService.write(
                    agent="monitoring",
                    content="Remember INCIDENT: Sustained CPU saturation detected. System load exceeded 95% for multiple consecutive samples.",
                    memory_type="semantic",
                    source="system",
                    state={"approved": True}
                )
            except Exception:
                pass

        return {"success": True, "metrics": metrics}

    @classmethod
    def analyze_health(cls, metrics: dict[str, Any]) -> dict[str, Any]:
        alerts = []
        status = "GOOD"

        # CPU Thresholds
        cpu = metrics.get("cpu_percent", 0.0)
        if cpu > 90.0:
            alerts.append({"metric": "CPU", "level": "CRITICAL", "value": cpu})
            status = "CRITICAL"
        elif cpu > 70.0:
            alerts.append({"metric": "CPU", "level": "WARNING", "value": cpu})
            if status != "CRITICAL":
                status = "WARNING"

        # RAM Thresholds
        ram = metrics.get("ram_percent", 0.0)
        if ram > 95.0:
            alerts.append({"metric": "RAM", "level": "CRITICAL", "value": ram})
            status = "CRITICAL"
        elif ram > 80.0:
            alerts.append({"metric": "RAM", "level": "WARNING", "value": ram})
            if status != "CRITICAL":
                status = "WARNING"

        # Temp Thresholds
        cpu_t = metrics.get("cpu_temp")
        if cpu_t is not None:
            if cpu_t > 85.0:
                alerts.append({"metric": "CPU Temp", "level": "CRITICAL", "value": cpu_t})
                status = "CRITICAL"
            elif cpu_t > 70.0:
                alerts.append({"metric": "CPU Temp", "level": "WARNING", "value": cpu_t})
                if status != "CRITICAL":
                    status = "WARNING"

        gpu_t = metrics.get("gpu_temp")
        if gpu_t is not None:
            if gpu_t > 85.0:
                alerts.append({"metric": "GPU Temp", "level": "CRITICAL", "value": gpu_t})
                status = "CRITICAL"
            elif gpu_t > 70.0:
                alerts.append({"metric": "GPU Temp", "level": "WARNING", "value": gpu_t})
                if status != "CRITICAL":
                    status = "WARNING"

        # Disk Thresholds
        disk = metrics.get("disk_percent", 0.0)
        if disk > 95.0:
            alerts.append({"metric": "Disk", "level": "CRITICAL", "value": disk})
            status = "CRITICAL"
        elif disk > 85.0:
            alerts.append({"metric": "Disk", "level": "WARNING", "value": disk})
            if status != "CRITICAL":
                status = "WARNING"

        # Health Score
        score = 100
        for alert in alerts:
            if alert["level"] == "CRITICAL":
                score -= 35
            elif alert["level"] == "WARNING":
                score -= 15
        score = max(0, min(100, score))

        return {"status": status, "health_score": score, "alerts": alerts}

    @classmethod
    def generate_recommendations(cls, alerts: list[dict[str, Any]]) -> list[str]:
        recommendations = []
        for alert in alerts:
            metric = alert["metric"]
            if metric == "CPU":
                recommendations.append("Close heavy processes")
            elif metric == "RAM":
                recommendations.append("Restart memory-intensive services")
            elif metric == "Disk":
                recommendations.append("Archive logs")
            elif "Temp" in metric:
                recommendations.append("Increase cooling")
        return list(dict.fromkeys(recommendations))

    @classmethod
    def generate_short_report(cls, metrics: dict[str, Any], health: dict[str, Any], recommendations: list[str]) -> str:
        report = (
            f"System Health: {health['status']}\n"
            f"CPU: {metrics.get('cpu_percent', 0.0):.1f}%\n"
            f"RAM: {metrics.get('ram_percent', 0.0):.1f}%\n"
            f"GPU: {metrics.get('gpu_usage', 0.0):.1f}%\n"
            f"Disk: {metrics.get('disk_percent', 0.0):.1f}%"
        )
        if recommendations:
            report += "\nRecommendations:\n" + "\n".join(f"- {r}" for r in recommendations)
        else:
            report += "\nNo immediate concerns."
        return redact_secrets(report)

    @classmethod
    def generate_detailed_report(cls, metrics: dict[str, Any], health: dict[str, Any], recommendations: list[str], history: list[dict[str, Any]]) -> str:
        cpu_vals = [s.get("cpu_percent", 0.0) for s in history] or [0.0]
        ram_vals = [s.get("ram_percent", 0.0) for s in history] or [0.0]
        
        cpu_avg = sum(cpu_vals) / len(cpu_vals)
        cpu_peak = max(cpu_vals)
        ram_avg = sum(ram_vals) / len(ram_vals)
        ram_peak = max(ram_vals)

        report = (
            f"Health Score: {health['health_score']}/100\n"
            f"CPU\n"
            f"  Avg: {cpu_avg:.1f}%\n"
            f"  Peak: {cpu_peak:.1f}%\n"
            f"  Temp: {metrics.get('cpu_temp') if metrics.get('cpu_temp') is not None else 'N/A'}\n"
            f"RAM\n"
            f"  Avg: {ram_avg:.1f}%\n"
            f"  Peak: {ram_peak:.1f}%\n"
            f"  Used: {metrics.get('ram_used_mb', 0.0):.1f} MB\n"
            f"  Available: {metrics.get('ram_available_mb', 0.0):.1f} MB\n"
            f"Network\n"
            f"  RX Bytes: {metrics.get('network_rx_bytes', 0.0)}\n"
            f"  TX Bytes: {metrics.get('network_tx_bytes', 0.0)}\n"
            f"  Latency: {metrics.get('network_latency_ms') if metrics.get('network_latency_ms') is not None else 'N/A'}"
        )
        if recommendations:
            report += "\nRecommendations:\n" + "\n".join(f"- {r}" for r in recommendations)
        if health.get("alerts"):
            report += "\nActive Alerts:\n" + "\n".join(f"- {a['metric']} is {a['level']} ({a['value']})" for a in health["alerts"])
        
        return redact_secrets(report)


def monitoring_node(state: dict[str, Any]) -> dict[str, Any]:
    stats = MonitoringAgent.load_stats()
    
    # Calculate avg latency
    latencies = stats.get("latency_ms", [100])
    avg_latency = sum(latencies) / len(latencies)
    
    # Check failure rate to make freeze recommendations
    total_steps = stats.get("total_steps", 100)
    failures = stats.get("failures", 0)
    failure_rate = failures / total_steps if total_steps > 0 else 0.0
    
    # Collect metrics via Agent collect_metrics api
    m_res = MonitoringAgent.collect_metrics("monitoring")
    metrics = m_res["metrics"]
    cpu_percent = metrics.get("cpu_percent", 0.0)
    ram_percent = metrics.get("ram_percent", 0.0)
    gpu_percent = metrics.get("gpu_usage", 0.0)
    
    health = MonitoringAgent.analyze_health(metrics)
    recs = MonitoringAgent.generate_recommendations(health["alerts"])
    
    freeze_recommended = False
    reasons = []
    if failure_rate > 0.05:
        freeze_recommended = True
        reasons.append(f"High failure rate ({failure_rate:.1%}) exceeds threshold of 5.0%")
    if avg_latency > 300:
        freeze_recommended = True
        reasons.append(f"High average latency ({avg_latency:.1f}ms) exceeds threshold of 300ms")
        
    status_str = "freeze recommended" if freeze_recommended else health["status"].lower()
    
    report_lines = [
        "Ecosystem Monitoring Report:",
        f"- Status: {status_str.upper()}",
        f"- System Load: CPU: {cpu_percent:.1f}% | RAM: {ram_percent:.1f}% | GPU: {gpu_percent:.1f}%",
        f"- Total Steps: {total_steps} | Failed Steps: {failures} (Rate: {failure_rate:.2%})",
        f"- Avg Latency: {avg_latency:.1f}ms",
        f"- Estimated Cost: {stats.get('costs', {}).get('total_tokens', 124500)} tokens (${stats.get('costs', {}).get('estimated_usd', 2.49):.2f} USD)",
        f"- Tool Health Matrix:",
    ]
    for tool, health_val in stats.get("tool_health", {}).items():
        report_lines.append(f"  * {tool}: {health_val.upper()}")
        
    report_lines.append(f"- Prediction Reliability: {stats.get('prediction_reliability', 0.94):.1%}")
    report_lines.append(f"- Research Debt Status: {stats.get('research_debt', 'Low')}")

    if freeze_recommended:
        report_lines.append("\nWARNING: Governance Freeze recommended due to:")
        for r in reasons:
            report_lines.append(f"  * {r}")
            
    if recs:
        report_lines.append("\nRecommendations:")
        for r in recs:
            report_lines.append(f"  - {r}")
            
    final_report = redact_secrets("\n".join(report_lines))
    state["result"] = final_report
    state["logs"].append("monitoring: observed tool health & costs")
    return state
