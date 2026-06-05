from __future__ import annotations

import json
from pathlib import Path

from .models import Reading


def load_readings(path: Path) -> list[Reading]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Reading(
            timestamp_ms=int(item["timestamp_ms"]),
            voltage_v=float(item["voltage_v"]),
            current_a=float(item["current_a"]),
            temperature_c=float(item["temperature_c"]),
            rf_noise_dbm=float(item["rf_noise_dbm"]),
            visual_hazard_confidence=float(item.get("visual_hazard_confidence", 0.0)),
            thermal_hotspot_c=float(item.get("thermal_hotspot_c", 0.0)),
            line_of_sight_m=float(item.get("line_of_sight_m", 0.0)),
        )
        for item in raw.get("readings", [])
    ]
