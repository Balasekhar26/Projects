from __future__ import annotations

from dataclasses import dataclass

from dews_safe_sim.models import SafetyFinding


@dataclass(frozen=True)
class AnimalAudioDetection:
    species: str
    sound_type: str
    confidence: float
    distress_score: float = 0.0
    zone: str = "unknown"


def animal_detection_to_finding(detection: AnimalAudioDetection) -> SafetyFinding | None:
    if detection.confidence < 0.5:
        return None

    if detection.distress_score >= 0.7:
        return SafetyFinding(
            level="alert",
            metric="animal_audio_distress",
            message=f"Possible {detection.species} distress sound detected in {detection.zone}",
            observed=detection.distress_score,
            recommendation="Review audio, inspect the area safely, and correlate with motion or thermal sensors.",
            protective_action="alert_and_evidence",
        )

    return SafetyFinding(
        level="review",
        metric="animal_audio_event",
        message=f"{detection.species} sound classified as {detection.sound_type}",
        observed=detection.confidence,
        recommendation="Log as environmental context unless other sensors raise the risk.",
        protective_action="log_event",
    )

