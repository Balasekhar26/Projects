"""Corpus Splitter (Program 27.0 / Phase 27A).

Stratified train / val / test split that preserves the distribution of
`result` labels (success / failure / recovered) across all three partitions.

Splitting is deterministic for a given seed, ensuring reproducible corpus
builds across runs.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Dict, List, Tuple

# Default split ratios
DEFAULT_TRAIN = 0.80
DEFAULT_VAL = 0.10
DEFAULT_TEST = 0.10

CorpusSplit = Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]


class CorpusSplitter:
    """Produces reproducible, stratified train/val/test partitions."""

    @classmethod
    def split(
        cls,
        records: List[Dict[str, Any]],
        train_ratio: float = DEFAULT_TRAIN,
        val_ratio: float = DEFAULT_VAL,
        test_ratio: float = DEFAULT_TEST,
        seed: int = 42,
    ) -> Tuple[CorpusSplit, Dict[str, Any]]:
        """Splits records into train, val, and test sets.

        Args:
            records:     Deduplicated, curriculum-sorted extraction records.
            train_ratio: Fraction for training (default 0.80).
            val_ratio:   Fraction for validation (default 0.10).
            test_ratio:  Fraction for test (default 0.10).
            seed:        Random seed for reproducibility (default 42).

        Returns:
            ((train, val, test), manifest_info) where manifest_info contains
            split sizes and label distributions.
        """
        if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-9:
            raise ValueError(
                f"Ratios must sum to 1.0; got {train_ratio + val_ratio + test_ratio:.4f}"
            )

        # Group by result label for stratification
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for rec in records:
            groups[rec.get("result", "unknown")].append(rec)

        train_all: List[Dict[str, Any]] = []
        val_all: List[Dict[str, Any]] = []
        test_all: List[Dict[str, Any]] = []

        rng = random.Random(seed)

        for label, group in groups.items():
            shuffled = list(group)
            rng.shuffle(shuffled)

            n = len(shuffled)
            n_train = max(1, round(n * train_ratio)) if n >= 3 else n
            n_val = max(0, round(n * val_ratio)) if n >= 3 else 0
            # test gets the remainder to avoid rounding drift
            n_test = n - n_train - n_val

            train_all.extend(shuffled[:n_train])
            val_all.extend(shuffled[n_train: n_train + n_val])
            test_all.extend(shuffled[n_train + n_val:])

        # Final shuffle within each split (preserves stratification, removes ordering)
        rng.shuffle(train_all)
        rng.shuffle(val_all)
        rng.shuffle(test_all)

        manifest_info = {
            "seed": seed,
            "train_ratio": train_ratio,
            "val_ratio": val_ratio,
            "test_ratio": test_ratio,
            "train_count": len(train_all),
            "val_count": len(val_all),
            "test_count": len(test_all),
            "label_groups": {label: len(g) for label, g in groups.items()},
        }

        return (train_all, val_all, test_all), manifest_info
