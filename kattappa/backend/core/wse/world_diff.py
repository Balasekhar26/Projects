"""WSE Component 4: WorldDiff.

Computes the difference between two world states at different timestamps,
identifying entities that were added, removed, or changed between t1 and t2.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.core.wse.timeline import WSETimeline

logger = logging.getLogger(__name__)


@dataclass
class WorldDiffReport:
    """Result of comparing world states at two timestamps."""
    t1: float
    t2: float
    added: List[str] = field(default_factory=list)     # entity_ids that appeared
    removed: List[str] = field(default_factory=list)   # entity_ids that disappeared
    changed: List[Dict[str, Any]] = field(default_factory=list)  # {entity_id, from, to}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "t1": self.t1,
            "t2": self.t2,
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "summary": {
                "added_count": len(self.added),
                "removed_count": len(self.removed),
                "changed_count": len(self.changed),
            },
        }


def _nested_diff(state_a: Dict[str, Any], state_b: Dict[str, Any]) -> Dict[str, Any]:
    """Computes field-level diff between two state dicts."""
    all_keys = set(state_a) | set(state_b)
    diffs: Dict[str, Any] = {}
    for k in all_keys:
        if k not in state_a:
            diffs[k] = {"added": state_b[k]}
        elif k not in state_b:
            diffs[k] = {"removed": state_a[k]}
        elif state_a[k] != state_b[k]:
            diffs[k] = {"from": state_a[k], "to": state_b[k]}
    return diffs


class WSEWorldDiff:
    """Computes state differences between two points in time."""

    def __init__(self, timeline: WSETimeline) -> None:
        self._timeline = timeline

    def diff(self, t1: float, t2: float) -> WorldDiffReport:
        """Returns a WorldDiffReport comparing world state at t1 vs t2."""
        if t2 <= t1:
            raise ValueError(f"t2 ({t2}) must be greater than t1 ({t1})")

        state_at_t1 = self._timeline.at(t1)
        state_at_t2 = self._timeline.at(t2)

        report = WorldDiffReport(t1=t1, t2=t2)

        all_entity_ids = set(state_at_t1) | set(state_at_t2)

        for entity_id in all_entity_ids:
            in_t1 = entity_id in state_at_t1
            in_t2 = entity_id in state_at_t2

            if in_t2 and not in_t1:
                report.added.append(entity_id)
            elif in_t1 and not in_t2:
                report.removed.append(entity_id)
            else:
                field_diff = _nested_diff(state_at_t1[entity_id], state_at_t2[entity_id])
                if field_diff:
                    report.changed.append({
                        "entity_id": entity_id,
                        "changes": field_diff,
                    })

        logger.debug(
            "WorldDiff [%.2f → %.2f]: +%d -%d ~%d",
            t1, t2, len(report.added), len(report.removed), len(report.changed),
        )
        return report
