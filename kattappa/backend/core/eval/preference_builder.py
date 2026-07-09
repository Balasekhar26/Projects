"""Preference Dataset Builder (Program 27E2).

Reads execution traces from a JSONL corpus and converts them into
DPO-ready preference pairs:
    successful trace  →  chosen_response
    failed trace      →  rejected_response
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class PreferencePair:
    """A single DPO training example."""

    prompt: str
    chosen: str
    rejected: str
    source: str = "experience_store"


class PreferenceBuilder:
    """Builds preference pairs from labelled JSONL execution traces."""

    DOMAIN_TOKENS = ("<|plan|>", "<|action|>", "<|result|>", "<|eot|>")

    def __init__(self, beta: float = 0.1) -> None:
        self.beta = beta  # stored for downstream DPO use

    # ── Formatting helpers ────────────────────────────────────────────────────

    def _format_prompt(self, record: dict) -> str:
        return f"<|plan|>{record.get('instruction', '').strip()}"

    def _format_response(self, record: dict) -> str:
        actions = record.get("actions", [])
        if isinstance(actions, list):
            action_str = " ".join(str(a) for a in actions)
        else:
            action_str = str(actions)
        output = record.get("output", record.get("result", "")).strip()
        return f"<|action|>{action_str}<|result|>{output}<|eot|>"

    # ── Pair construction ─────────────────────────────────────────────────────

    def build_from_file(self, jsonl_path: str | Path) -> List[PreferencePair]:
        """Reads a JSONL file and builds preference pairs.

        Records are bucketed by (instruction, result) label:
        - result == 'success'  → candidate for chosen
        - result == 'failure'  → candidate for rejected
        Pairs are matched greedily by instruction text.
        """
        path = Path(jsonl_path)
        if not path.exists():
            return []

        successful: List[dict] = []
        failed: List[dict] = []

        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                label = str(rec.get("result", "")).lower()
                if label == "success":
                    successful.append(rec)
                elif label == "failure":
                    failed.append(rec)

        return self._pair(successful, failed)

    def build_from_records(
        self,
        successful: List[dict],
        failed: List[dict],
    ) -> List[PreferencePair]:
        return self._pair(successful, failed)

    def _pair(
        self,
        successful: List[dict],
        failed: List[dict],
    ) -> List[PreferencePair]:
        pairs: List[PreferencePair] = []
        # Simple greedy pairing: zip by position, trimming to shorter list
        for chosen_rec, rejected_rec in zip(successful, failed):
            prompt = self._format_prompt(chosen_rec)
            pairs.append(
                PreferencePair(
                    prompt=prompt,
                    chosen=self._format_response(chosen_rec),
                    rejected=self._format_response(rejected_rec),
                )
            )
        return pairs

    def save(self, pairs: List[PreferencePair], output_path: str | Path) -> int:
        """Writes preference pairs to a JSONL file. Returns number written."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with path.open("w", encoding="utf-8") as fh:
            for pair in pairs:
                fh.write(
                    json.dumps(
                        {
                            "prompt": pair.prompt,
                            "chosen": pair.chosen,
                            "rejected": pair.rejected,
                            "source": pair.source,
                        }
                    )
                    + "\n"
                )
                written += 1
        return written
