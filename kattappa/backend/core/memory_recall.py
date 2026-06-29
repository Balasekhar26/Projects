"""Memory Recall Layer (Layer 3).

Concurrently fetches episodic history, semantic vector matches, relationship profiles,
and cognitive lessons to populate the working memory context.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Dict, List, Optional

from backend.core.memory import memory
from backend.core.episodic_memory import EpisodicMemory
from backend.core.relationship_memory import RelationshipMemory


class MemoryRecall:
    @classmethod
    def _fetch_episodic_messages(cls, session_id: str) -> list[dict[str, Any]]:
        try:
            all_msgs = memory.list_chat_messages(session_id, limit=30)
            return all_msgs[-10:] if all_msgs else []
        except Exception:
            return []

    @classmethod
    def _fetch_semantic_context(
        cls, clean_message: str, session_id: str
    ) -> list[dict[str, Any]]:
        try:
            if not clean_message.strip():
                return []
            return memory.search_chat_messages(
                clean_message,
                limit=3,
                session_id=session_id,
            )
        except Exception:
            return []

    @classmethod
    def _fetch_cognitive_episodes(
        cls, clean_message: str, session_id: str
    ) -> list[dict[str, Any]]:
        try:
            if not clean_message.strip():
                return []
            # Query the detailed autobiographical events/episodes
            return EpisodicMemory.recall(
                clean_message,
                limit=3,
                relevance_floor=0.35,
                source_types=["DID", "READ", "SIMULATED", "INFERRED"],
                session_id=session_id,
            )
        except Exception:
            return []

    @classmethod
    def _fetch_relationship_notes(cls) -> dict[str, Any]:
        try:
            profile = RelationshipMemory.assemble("bala")
            return profile if profile else {}
        except Exception:
            return {}

    @classmethod
    def recall(cls, attention_frame: Dict[str, Any], session_id: str, query: str | None = None) -> Dict[str, Any]:
        """Fetch and merge memory context parallelly in < 50 ms."""
        clean_message = query if query is not None else attention_frame.get("clean_message", "")

        has_failed = False

        # Default values in case any future times out or fails
        episodic_history: list = []
        semantic_context: list = []
        cognitive_episodes: list = []
        relationship_notes: list = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_episodic = executor.submit(cls._fetch_episodic_messages, session_id)
            future_semantic = executor.submit(
                cls._fetch_semantic_context, clean_message, session_id
            )
            future_cognitive = executor.submit(
                cls._fetch_cognitive_episodes, clean_message, session_id
            )
            future_relationship = executor.submit(cls._fetch_relationship_notes)

            # Limit thread waiting to fit budget
            try:
                episodic_history = future_episodic.result(timeout=0.045)
            except Exception:
                has_failed = True

            try:
                semantic_context = future_semantic.result(timeout=0.045)
            except Exception:
                has_failed = True

            try:
                cognitive_episodes = future_cognitive.result(timeout=0.045)
            except Exception:
                has_failed = True

            try:
                relationship_notes = future_relationship.result(timeout=0.045)
            except Exception:
                has_failed = True


        return {
            "episodic_history": episodic_history,
            "semantic_context": semantic_context,
            "cognitive_episodes": cognitive_episodes,
            "relationship_notes": relationship_notes,
            "memory_confidence_level": "LOW" if has_failed else "HIGH"
        }
