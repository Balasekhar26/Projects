from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BirdNetDetection:
    label: str
    confidence: float
    start_s: float | None = None
    end_s: float | None = None


@dataclass(frozen=True)
class AnimalMeaningEstimate:
    species: str
    possible_meanings: tuple[str, ...]
    confidence: float
    explanation: str
    source_label: str


class BirdNetRunner:
    def __init__(self, upstream_root: str | Path) -> None:
        self.upstream_root = Path(upstream_root)

    def analyze_command(
        self,
        audio_path: str | Path,
        output_dir: str | Path,
        min_confidence: float = 0.5,
    ) -> list[str]:
        return [
            "python",
            "-m",
            "birdnet_analyzer.analyze",
            str(audio_path),
            "-o",
            str(output_dir),
            "--min_conf",
            str(min_confidence),
        ]

    def install_command(self) -> list[str]:
        return ["python", "-m", "pip", "install", "-e", str(self.upstream_root)]


def estimate_meaning(detection: BirdNetDetection) -> AnimalMeaningEstimate:
    label = detection.label.strip()
    species = _common_name(label)
    lower = label.lower()

    if any(word in lower for word in ("owl", "hawk", "eagle", "falcon")):
        meanings = ("territorial call", "hunting or alarm context", "presence nearby")
    elif any(word in lower for word in ("crow", "jay", "myna")):
        meanings = ("social call", "alarm call", "group communication")
    elif any(word in lower for word in ("dog", "canis")):
        meanings = ("alert", "stress", "excitement")
    elif any(word in lower for word in ("cat", "felis")):
        meanings = ("attention seeking", "stress", "territorial signal")
    else:
        meanings = ("species presence", "environmental context", "unknown intent")

    confidence = round(max(0.0, min(1.0, detection.confidence * 0.85)), 3)
    return AnimalMeaningEstimate(
        species=species,
        possible_meanings=meanings,
        confidence=confidence,
        explanation=(
            "This is a meaning estimate from acoustic classification, not a literal translation. "
            "Use behavior, location, time, and repeated samples before trusting it."
        ),
        source_label=label,
    )


def _common_name(label: str) -> str:
    if "_" in label:
        return label.split("_", 1)[1].strip()
    return label

