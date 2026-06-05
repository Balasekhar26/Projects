from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    timestamp_ms: int
    voltage_v: float
    current_a: float
    temperature_c: float
    rf_noise_dbm: float
    visual_hazard_confidence: float = 0.0
    thermal_hotspot_c: float = 0.0
    line_of_sight_m: float = 0.0


@dataclass(frozen=True)
class SafetyLimit:
    name: str
    minimum: float | None = None
    maximum: float | None = None

    def contains(self, value: float) -> bool:
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value > self.maximum:
            return False
        return True


@dataclass(frozen=True)
class SafetyFinding:
    level: str
    metric: str
    message: str
    observed: float
    recommendation: str
    protective_action: str = "review"
