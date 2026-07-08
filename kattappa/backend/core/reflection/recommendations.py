"""Recommendation Generation Engine (Program 6).

Generates optimization recommendations and actionable learning candidates.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from backend.core.reflection.models import ExecutionReview, LearningCandidate

logger = logging.getLogger(__name__)


class RecommendationGenerator:
    """Produces actionable plan/system optimization recommendations based on reviews."""

    @staticmethod
    def generate(review: ExecutionReview) -> List[LearningCandidate]:
        """Examines review metrics to construct specific policy/model learning candidates."""
        candidates = []

        # 1. Failure recommendations
        if review.failure_category == "Network":
            candidates.append(
                LearningCandidate(
                    candidate_id=f"lc_{uuid.uuid4().hex[:8]}",
                    target_type="RetryLimit",
                    explanation="High frequency of network-related failures detected. Recommended to increase retry limits.",
                    proposed_update={"max_retries": 5, "backoff_policy": "exponential"},
                    confidence=0.85,
                    priority="High",
                )
            )
        elif review.failure_category == "Permission":
            candidates.append(
                LearningCandidate(
                    candidate_id=f"lc_{uuid.uuid4().hex[:8]}",
                    target_type="ConstraintRule",
                    explanation="Execution failed due to missing authorization. Recommended to verify permissions before running.",
                    proposed_update={"verify_permissions_preflight": True},
                    confidence=0.90,
                    priority="High",
                )
            )
        elif review.failure_category == "API":
            candidates.append(
                LearningCandidate(
                    candidate_id=f"lc_{uuid.uuid4().hex[:8]}",
                    target_type="ToolPolicy",
                    explanation="Rate limit error detected. Recommended to increase request backoffs and enable local caching.",
                    proposed_update={"rate_limit_backoff_delay": 5.0, "enable_local_cache": True},
                    confidence=0.88,
                    priority="High",
                )
            )


        # 2. Performance bottlenecks recommendations
        for node in review.bottleneck_nodes:
            candidates.append(
                LearningCandidate(
                    candidate_id=f"lc_{uuid.uuid4().hex[:8]}",
                    target_type="ToolPolicy",
                    explanation=f"Node '{node}' acted as execution bottleneck. Recommended caching or parallel execution.",
                    proposed_update={"cache_results": True, "optimize_parallel": True, "target_node": node},
                    confidence=0.75,
                    priority="Medium",
                )
            )

        # 3. Parallelization recommendations
        if review.parallelization_score < 0.3:
            candidates.append(
                LearningCandidate(
                    candidate_id=f"lc_{uuid.uuid4().hex[:8]}",
                    target_type="ModelRoute",
                    explanation="Plan execution has high sequential ratio. Recommended to analyze dependency graph for concurrency.",
                    proposed_update={"split_independent_layers": True},
                    confidence=0.70,
                    priority="Low",
                )
            )

        return candidates
