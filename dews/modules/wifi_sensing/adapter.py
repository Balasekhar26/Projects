from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dews_safe_sim.models import SafetyFinding


@dataclass(frozen=True)
class WifiCsiPrediction:
    activity: str
    confidence: float
    zone: str = "unknown"
    timestamp_ms: int = 0
    source: str = "CSI-Sense-Zero"


def build_csi_sense_zero_command(
    upstream_root: str | Path,
    artifact_dir: str = "artifacts/v1",
    host: str = "127.0.0.1",
    port: int = 9999,
    frequency_hz: int = 2,
) -> list[str]:
    root = Path(upstream_root)
    return [
        "python",
        str(root / "main.py"),
        "--load",
        str(root / artifact_dir),
        "--host",
        host,
        "--port",
        str(port),
        "--frequency",
        str(frequency_hz),
    ]


def prediction_to_finding(prediction: WifiCsiPrediction) -> SafetyFinding | None:
    activity = prediction.activity.strip().lower()
    if prediction.confidence < 0.55:
        return None

    if activity in {"fall", "falling", "fallen"}:
        return SafetyFinding(
            level="alert",
            metric="wifi_csi_fall",
            message=f"Possible fall detected in {prediction.zone}",
            observed=prediction.confidence,
            recommendation="Check the zone, preserve sensor evidence, and request human review.",
            protective_action="alert_and_check",
        )

    if activity in {"walking", "moving", "presence", "standing", "sitting"}:
        return SafetyFinding(
            level="review",
            metric="wifi_csi_presence",
            message=f"Human movement detected in {prediction.zone}",
            observed=prediction.confidence,
            recommendation="Correlate with camera, thermal, microphone, or schedule context before escalating.",
            protective_action="correlate_sensors",
        )

    return SafetyFinding(
        level="review",
        metric="wifi_csi_activity",
        message=f"CSI activity classified as {prediction.activity} in {prediction.zone}",
        observed=prediction.confidence,
        recommendation="Log the event and compare with calibrated baseline.",
        protective_action="log_event",
    )

