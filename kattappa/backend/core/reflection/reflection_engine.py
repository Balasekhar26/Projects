"""Reflection Engine Orchestration (Program 6).

Coordinates execution record collection, reviews, classifications, and recommendation runs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.reflection.models import ExecutionRecord, ExecutionReview, LearningCandidate
from backend.core.reflection.analyzer import FailureClassifier, OptimizationAnalyzer
from backend.core.reflection.recommendations import RecommendationGenerator

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """Coordinates the execution logging telemetry analysis and learns optimization options."""

    _instance: Optional[ReflectionEngine] = None

    def __init__(self) -> None:
        # In-memory history of compiled execution records
        self.records: Dict[str, ExecutionRecord] = {}
        # In-memory history of compiled execution reviews
        self.reviews: Dict[str, ExecutionReview] = {}
        # In-memory history of generated learning candidates
        self.candidates: Dict[str, List[LearningCandidate]] = {}

    @classmethod
    def get_instance(cls) -> ReflectionEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def process_execution(self, record: ExecutionRecord) -> ExecutionReview:
        """Processes finished execution record telemetry and compiles reviews & recommendations."""
        logger.info("Starting reflection processing on session: %s", record.session_id)
        self.records[record.session_id] = record

        # 1. Compile Review
        success_nodes_count = len(record.task_durations)
        total_nodes = success_nodes_count + len(record.failures)
        success_rate = (success_nodes_count / total_nodes * 100.0) if total_nodes > 0 else 100.0

        avg_latency = (
            sum(record.task_durations.values()) / success_nodes_count
            if success_nodes_count > 0 else 0.0
        )

        total_retries = sum(record.retries.values())

        # Failure classification
        failure_cat = FailureClassifier.classify(record.failures)

        # Performance bottlenecks
        bottlenecks = OptimizationAnalyzer.find_bottlenecks(record.task_durations)

        # Parallelization score
        parallel_score = OptimizationAnalyzer.analyze_parallelization(record)

        # Quality score math
        quality_score = 1.0
        if success_rate < 100.0:
            quality_score -= 0.3 * (1.0 - success_rate / 100.0)
        if total_retries > 0:
            quality_score -= 0.05 * total_retries
        if bottlenecks:
            quality_score -= 0.1 * len(bottlenecks)
        quality_score = max(0.1, quality_score)

        review = ExecutionReview(
            session_id=record.session_id,
            success_rate=success_rate,
            avg_latency=avg_latency,
            total_retries=total_retries,
            failure_category=failure_cat,
            bottleneck_nodes=bottlenecks,
            parallelization_score=parallel_score,
            quality_score=quality_score,
        )

        self.reviews[record.session_id] = review

        # 2. Compile Recommendations
        session_candidates = RecommendationGenerator.generate(review)
        self.candidates[record.session_id] = session_candidates

        return review

    def get_candidates(self, session_id: str) -> List[LearningCandidate]:
        """Retrieves candidates recommendations for the target session."""
        return self.candidates.get(session_id, [])

    def get_all_reviews(self) -> List[ExecutionReview]:
        """Returns all completed execution reviews."""
        return list(self.reviews.values())
