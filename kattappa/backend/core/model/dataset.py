"""Kattappa Dataset Loader (Program 27D).

Converts instruction, reasoning trace, and actions JSONL corpora into padded
token matrices for language model training.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import torch
from torch.utils.data import Dataset


class KattappaDataset(Dataset):
    """Tokenizes and loads JSONL records for autoregressive training."""

    def __init__(
        self,
        jsonl_path: str | Path,
        tokenizer: Any,
        max_len: int = 1024,
        format_type: str = "instruction_tuning",
    ) -> None:
        """Args:

            jsonl_path:  Path to the JSONL data file.
            tokenizer:   A SentencePiece or MockTokenizer instance.
            max_len:     Maximum sequence length limit.
            format_type: Dataset format style: 'instruction_tuning' or 'chain_of_thought'.
        """
        self.jsonl_path = Path(jsonl_path)
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.format_type = format_type
        self.records: List[Dict[str, Any]] = []

        # Special tokens matching configurations
        self.pad_id = 0
        self.unk_id = 1
        self.bos_id = 2
        self.eos_id = 3

        self._load_records()

    def _load_records(self) -> None:
        if not self.jsonl_path.exists():
            return
        with self.jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    def __len__(self) -> int:
        return len(self.records)

    def _format_text(self, record: Dict[str, Any]) -> str:
        """Assembles textual representation of the training sample."""
        if self.format_type == "chain_of_thought":
            instruction = record.get("instruction", "").strip()
            reasoning = record.get("reasoning", "").strip()
            output = record.get("output", "").strip()
            return f"<|plan|>{instruction}<|action|>{reasoning}<|result|>{output}<|eot|>"
        else:
            # Default instruction tuning
            instruction = record.get("instruction", "").strip()
            # Support both output/result keys
            output = record.get("output", record.get("result", "")).strip()
            return f"<|plan|>{instruction}<|action|>{output}<|eot|>"

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        rec = self.records[idx]
        text = self._format_text(rec)

        # Encode tokens
        token_ids = self.tokenizer.encode(text, out_type=int)

        # Prepend BOS token
        token_ids = [self.bos_id] + token_ids

        # Truncate if exceeds max_len
        if len(token_ids) > self.max_len:
            token_ids = token_ids[: self.max_len]

        input_ids = torch.tensor(token_ids, dtype=torch.long)

        # For auto-regressive language modeling, targets are shifted input_ids.
        # We fill labels with input_ids and mask padding/BOS tokens during loss check.
        labels = input_ids.clone()
        # Ignore loss on first BOS token
        labels[0] = -100

        return {"input_ids": input_ids, "labels": labels}


class KattappaCollate:
    """Collates and dynamically pads lists of samples into uniform batch tensors."""

    def __init__(self, pad_id: int = 0) -> None:
        self.pad_id = pad_id

    def __call__(self, batch: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
        input_ids_list = [item["input_ids"] for item in batch]
        labels_list = [item["labels"] for item in batch]

        # Dynamically pad to max length in this batch
        max_len = max(len(x) for x in input_ids_list)

        padded_inputs = []
        padded_labels = []

        for input_ids, labels in zip(input_ids_list, labels_list):
            diff = max_len - len(input_ids)
            if diff > 0:
                # Pad input_ids with pad_id
                padded_in = torch.cat([input_ids, torch.full((diff,), self.pad_id, dtype=torch.long)])
                # Pad labels with ignore index -100
                padded_la = torch.cat([labels, torch.full((diff,), -100, dtype=torch.long)])
            else:
                padded_in = input_ids
                padded_la = labels

            padded_inputs.append(padded_in)
            padded_labels.append(padded_la)

        return {
            "input_ids": torch.stack(padded_inputs),
            "labels": torch.stack(padded_labels),
        }
