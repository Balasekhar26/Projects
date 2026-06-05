from __future__ import annotations

from .models import Reading, SafetyFinding, SafetyLimit


class SafetySimulation:
    """Simulation-only safety checker for energy/environment readings."""

    def __init__(self, limits: dict[str, SafetyLimit] | None = None) -> None:
        self.limits = limits or {
            "voltage_v": SafetyLimit("voltage_v", minimum=0.0, maximum=24.0),
            "current_a": SafetyLimit("current_a", minimum=0.0, maximum=2.0),
            "temperature_c": SafetyLimit("temperature_c", maximum=70.0),
            "rf_noise_dbm": SafetyLimit("rf_noise_dbm", maximum=-20.0),
            "visual_hazard_confidence": SafetyLimit("visual_hazard_confidence", minimum=0.0, maximum=0.82),
            "thermal_hotspot_c": SafetyLimit("thermal_hotspot_c", maximum=85.0),
        }

    def analyze(self, readings: list[Reading]) -> list[SafetyFinding]:
        findings: list[SafetyFinding] = []
        for reading in readings:
            for metric, limit in self.limits.items():
                value = float(getattr(reading, metric))
                if not limit.contains(value):
                    findings.append(self._finding(metric, value, reading.timestamp_ms))
        return findings

    def _finding(self, metric: str, value: float, timestamp_ms: int) -> SafetyFinding:
        recommendations = {
            "voltage_v": "Check supply configuration and isolate the device if overvoltage persists.",
            "current_a": "Reduce load, inspect for shorts, and use current-limited supply mode.",
            "temperature_c": "Stop the run, let hardware cool, and inspect thermal paths.",
            "rf_noise_dbm": "Increase shielding distance, inspect grounding, and log the source environment.",
            "visual_hazard_confidence": "Do not engage the object. Mark the area, preserve camera evidence, and request trained human review.",
            "thermal_hotspot_c": "Increase safety distance, stop nearby operations, and monitor for escalation.",
        }
        protective_actions = {
            "voltage_v": "isolate_power",
            "current_a": "current_limit",
            "temperature_c": "cooldown",
            "rf_noise_dbm": "shield_and_log",
            "visual_hazard_confidence": "alert_and_evidence",
            "thermal_hotspot_c": "evacuate_and_monitor",
        }
        level = "alert" if metric in {"visual_hazard_confidence", "thermal_hotspot_c"} else "review"
        return SafetyFinding(
            level=level,
            metric=metric,
            message=f"{metric} exceeded safe simulation limit at {timestamp_ms} ms",
            observed=value,
            recommendation=recommendations[metric],
            protective_action=protective_actions[metric],
        )
