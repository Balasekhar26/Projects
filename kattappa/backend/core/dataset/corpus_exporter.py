"""Corpus Exporter (Program 27.0 / Phase 27A).

End-to-end pipeline that converts ExperienceStore trajectories into a
reproducible, training-ready corpus with a machine-readable manifest.

Pipeline:
    ExperienceStore
    → TraceExtractor          (raw records)
    → QualityFilter           (score / action gates)
    → Deduplicator            (exact + near-dedup)
    → CurriculumGenerator     (complexity annotation)
    → SyntheticAugmentation   (paraphrase expansion, after dedup)
    → CorpusSplitter          (train / val / test)
    → DatasetBuilder × 3      (JSONL files per split)
    → DatasetVersioning       (version metadata)
    → Manifest JSON           (full reproducibility record)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from backend.core.config import runtime_data_root
from backend.core.dataset.corpus_splitter import CorpusSplitter
from backend.core.dataset.curriculum_generator import CurriculumGenerator
from backend.core.dataset.dataset_builder import DatasetBuilder, DatasetFormat
from backend.core.dataset.dataset_metrics import DatasetMetrics
from backend.core.dataset.dataset_versioning import DatasetVersioning
from backend.core.dataset.deduplicator import Deduplicator
from backend.core.dataset.quality_filter import QualityFilter
from backend.core.dataset.synthetic_augmentation import SyntheticAugmentation
from backend.core.dataset.token_estimator import TokenEstimator
from backend.core.dataset.trace_extractor import TraceExtractor
from backend.core.learning.experience_store import ExperienceStore


def _manifest_path(version_id: str) -> Path:
    p = runtime_data_root() / "backend" / "data" / "datasets"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{version_id}_manifest.json"


class CorpusExporter:
    """Orchestrates the full corpus preparation and export pipeline."""

    @classmethod
    def export(
        cls,
        store: ExperienceStore,
        fmt: DatasetFormat = "instruction_tuning",
        version_id: str | None = None,
        min_score: float = 0.5,
        allow_failed: bool = False,
        augment_variants: int = 2,
        train_ratio: float = 0.80,
        val_ratio: float = 0.10,
        test_ratio: float = 0.10,
        split_seed: int = 42,
        model_params: int | None = None,
    ) -> Dict[str, Any]:
        """Runs the full pipeline from ExperienceStore to JSONL corpus files.

        Args:
            store:            Source of execution trajectories.
            fmt:              Dataset format for JSONL output.
            version_id:       Corpus version identifier (auto-generated if None).
            min_score:        Quality filter threshold (default 0.5).
            allow_failed:     Include failed trajectories in corpus.
            augment_variants: Paraphrase variants per record (default 2).
            train_ratio:      Training split fraction.
            val_ratio:        Validation split fraction.
            test_ratio:       Test split fraction.
            split_seed:       Random seed for reproducibility.
            model_params:     Model scale for FLOPs estimation (optional).

        Returns:
            manifest: Dict capturing every pipeline parameter and output metric.
        """
        version_id = version_id or f"corpus_{int(time.time())}"
        started_at = time.time()

        # ── 1. Extract ────────────────────────────────────────────────────────
        all_trajectories = store.trajectories
        raw_records = TraceExtractor.extract_all(all_trajectories)

        # ── 2. Quality filter ─────────────────────────────────────────────────
        filtered = QualityFilter.filter(
            raw_records,
            min_score=min_score,
            allow_failed=allow_failed,
        )

        # ── 3. Dedup ─────────────────────────────────────────────────────────
        unique, dedup_stats = Deduplicator.deduplicate(filtered)

        # ── 4. Curriculum annotation ──────────────────────────────────────────
        annotated = CurriculumGenerator.annotate(unique)

        # ── 5. Augmentation (after dedup to avoid deduping augments) ─────────
        augmented = SyntheticAugmentation.augment(annotated, variants_per_record=augment_variants)

        # ── 6. Split ─────────────────────────────────────────────────────────
        (train, val, test), split_info = CorpusSplitter.split(
            augmented,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
            seed=split_seed,
        )

        # ── 7. Build JSONL files ──────────────────────────────────────────────
        DatasetBuilder.build(train, fmt=fmt, version_id=f"{version_id}_train")
        DatasetBuilder.build(val, fmt=fmt, version_id=f"{version_id}_val")
        DatasetBuilder.build(test, fmt=fmt, version_id=f"{version_id}_test")

        # ── 8. Metrics ────────────────────────────────────────────────────────
        corpus_metrics = DatasetMetrics.compute(augmented)
        token_report = TokenEstimator.estimate(train, model_params=model_params)

        # ── 9. Version registry ───────────────────────────────────────────────
        DatasetVersioning.register_version(
            version_id=version_id,
            sample_count=len(augmented),
            fmt=fmt,
            source_trajectory_count=len(all_trajectories),
            notes=f"train={split_info['train_count']} val={split_info['val_count']} test={split_info['test_count']}",
        )

        # ── 10. Manifest ──────────────────────────────────────────────────────
        manifest: Dict[str, Any] = {
            "version_id": version_id,
            "generated_at": started_at,
            "pipeline": {
                "format": fmt,
                "min_score": min_score,
                "allow_failed": allow_failed,
                "augment_variants": augment_variants,
            },
            "counts": {
                "source_trajectories": len(all_trajectories),
                "after_extraction": len(raw_records),
                "after_quality_filter": len(filtered),
                "after_dedup": len(unique),
                "after_augmentation": len(augmented),
            },
            "dedup_stats": dedup_stats,
            "split": split_info,
            "corpus_metrics": corpus_metrics,
            "token_report": token_report,
        }

        # Persist manifest
        _manifest_path(version_id).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        return manifest
