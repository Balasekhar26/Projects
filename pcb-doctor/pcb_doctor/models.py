from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExpectedRange:
    minimum: float | None = None
    maximum: float | None = None
    nominal: float | None = None
    tolerance: float | None = None

    def contains(self, value: float) -> bool:
        low = self.minimum
        high = self.maximum
        if self.nominal is not None and self.tolerance is not None:
            low = self.nominal - self.tolerance
            high = self.nominal + self.tolerance
        if low is not None and value < low:
            return False
        if high is not None and value > high:
            return False
        return True


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    label: str
    expected_voltage: ExpectedRange | None = None
    expected_resistance: ExpectedRange | None = None
    expected_current: ExpectedRange | None = None
    upstream: tuple[str, ...] = ()
    components: tuple[str, ...] = ()


@dataclass(frozen=True)
class Measurement:
    node_id: str
    voltage: float | None = None
    resistance: float | None = None
    current: float | None = None
    note: str = ""
    thermal_delta_c: float | None = None
    visual_damage_confidence: float | None = None
    programmer_status: str = ""


@dataclass(frozen=True)
class FaultFinding:
    node_id: str
    severity: str
    score: int
    kind: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    probable_causes: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticReport:
    findings: tuple[FaultFinding, ...]
    root_cause_path: tuple[str, ...]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "root_cause_path": list(self.root_cause_path),
            "findings": [
                {
                    "node_id": item.node_id,
                    "severity": item.severity,
                    "score": item.score,
                    "kind": item.kind,
                    "message": item.message,
                    "evidence": item.evidence,
                    "probable_causes": list(item.probable_causes),
                    "next_steps": list(item.next_steps),
                }
                for item in self.findings
            ],
        }
