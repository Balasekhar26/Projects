"""MCE Component 4: Semantic Extractor.

Uses the local LLM to extract structured (subject, relation, object) knowledge
triples from promoted episodic text. Falls back to keyword-based extraction
if the model returns invalid JSON or times out.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List

from backend.core.logger import log_event
from backend.core.model_router import ask_model

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeTriple:
    subject: str
    relation: str
    obj: str       # 'object' is a Python builtin — use obj
    confidence: float = 0.75
    source_episode_id: str = ""


class MCESemanticExtractor:
    """Extracts knowledge triples from episodic text for KG ingestion."""

    _RELATION_KEYWORDS = [
        "uses", "depends on", "related to", "causes", "prevents", "triggers",
        "is a", "part of", "improves", "knows", "built", "learned from",
        "requires", "works on", "created", "supports",
    ]

    @classmethod
    def extract(cls, content: str, source_episode_id: str = "") -> List[KnowledgeTriple]:
        """Extracts knowledge triples using LLM with keyword fallback."""
        triples: List[KnowledgeTriple] = []

        # 1. LLM-based extraction
        prompt = (
            "Extract factual knowledge triples from the following text. "
            "Return a JSON array of objects with keys 'subject', 'relation', 'object'. "
            "Only include clear factual relationships. "
            "If there are no clear facts, return an empty array [].\n\n"
            f"Text: {content[:800]}\n\nJSON:"
        )
        try:
            response = ask_model(prompt, role="general")
            clean = response.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            parsed = json.loads(clean)
            if isinstance(parsed, list):
                for item in parsed:
                    subj = str(item.get("subject", "")).strip()
                    rel = str(item.get("relation", "")).strip()
                    obj = str(item.get("object", "")).strip()
                    if subj and rel and obj:
                        triples.append(KnowledgeTriple(
                            subject=subj, relation=rel, obj=obj,
                            confidence=0.78, source_episode_id=source_episode_id,
                        ))
        except Exception as exc:
            logger.debug("SemanticExtractor LLM failed: %s — using keyword fallback", exc)

        # 2. Keyword-based fallback (always runs if LLM produced nothing)
        if not triples:
            triples = cls._keyword_fallback(content, source_episode_id)

        log_event("mce_triples_extracted", f"Extracted {len(triples)} triples from episode {source_episode_id}")
        return triples

    @classmethod
    def _keyword_fallback(cls, content: str, source_id: str) -> List[KnowledgeTriple]:
        """Simple pattern-based triple extraction."""
        triples: List[KnowledgeTriple] = []
        sentences = re.split(r"[.!?\n]", content)

        for sent in sentences:
            sent = sent.strip()
            if len(sent.split()) < 4:
                continue
            for kw in cls._RELATION_KEYWORDS:
                pattern = re.compile(
                    rf"(.+?)\s+{re.escape(kw)}\s+(.+)", re.IGNORECASE
                )
                m = pattern.search(sent)
                if m:
                    subj = m.group(1).strip()[:80]
                    obj = m.group(2).strip()[:80]
                    if subj and obj:
                        triples.append(KnowledgeTriple(
                            subject=subj,
                            relation=kw.upper().replace(" ", "_"),
                            obj=obj,
                            confidence=0.60,
                            source_episode_id=source_id,
                        ))
                    break  # one triple per sentence

        return triples[:10]  # cap at 10 per episode to avoid noise flooding
