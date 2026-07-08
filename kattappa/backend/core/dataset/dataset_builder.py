"""Dataset Builder (Program 26.0).

Converts filtered extraction records into finalized JSONL training corpora.
Supports multiple output formats for different fine-tuning objectives.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Literal

from backend.core.config import runtime_data_root

DatasetFormat = Literal["instruction_tuning", "chain_of_thought", "tool_calling", "planning"]


def _datasets_dir() -> Path:
    p = runtime_data_root() / "backend" / "data" / "datasets"
    p.mkdir(parents=True, exist_ok=True)
    return p


class DatasetBuilder:
    """Serialises records into JSONL files for various fine-tuning objectives."""

    @classmethod
    def build(
        cls,
        records: List[Dict[str, Any]],
        fmt: DatasetFormat = "instruction_tuning",
        version_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Converts extraction records into format-specific training samples.

        Returns the list of serialisable sample dicts (also written to JSONL).
        """
        version_id = version_id or f"v_{int(time.time())}"
        samples: List[Dict[str, Any]] = []

        for rec in records:
            sample = cls._format_record(rec, fmt)
            if sample:
                samples.append(sample)

        # Write JSONL
        path = _datasets_dir() / f"{version_id}_{fmt}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for s in samples:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")

        return samples

    @classmethod
    def _format_record(
        cls, rec: Dict[str, Any], fmt: DatasetFormat
    ) -> Dict[str, Any] | None:
        instruction = rec.get("instruction", "").strip()
        if not instruction:
            return None

        if fmt == "instruction_tuning":
            return {
                "instruction": instruction,
                "input": json.dumps(rec.get("context", {})),
                "output": rec.get("result", ""),
            }

        elif fmt == "chain_of_thought":
            return {
                "instruction": instruction,
                "reasoning": rec.get("reasoning_trace", ""),
                "output": rec.get("result", ""),
            }

        elif fmt == "tool_calling":
            return {
                "instruction": instruction,
                "tool_calls": rec.get("actions", []),
                "result": rec.get("result", ""),
                "metrics": rec.get("metrics", {}),
            }

        elif fmt == "planning":
            return {
                "goal": instruction,
                "plan_steps": rec.get("actions", []),
                "outcome": rec.get("result", ""),
                "cost": rec.get("metrics", {}).get("cost", 0.0),
                "duration": rec.get("metrics", {}).get("duration", 0.0),
            }

        return None
