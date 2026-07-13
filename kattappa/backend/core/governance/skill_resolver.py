from __future__ import annotations

import re
from typing import Any, Dict, List

STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "of", "for", "i", "in", "is", "it", "on", "with",
    "at", "by", "want", "find", "make", "get", "run", "do", "execute"
}


def resolve_skill_by_intent(intent: str, active_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolves skills matching user intent semantic keywords, sorting candidates by relevance."""
    intent_words = {w for w in re.findall(r"\w+", intent.lower()) if w not in STOPWORDS}
    if not intent_words:
        return []

    ranked = []
    for skill in active_skills:
        name = skill["name"].lower()
        desc = (skill.get("description") or "").lower()
        
        # Calculate overlap score
        name_words = {w for w in re.split(r"\W+", name) if w not in STOPWORDS}
        desc_words = {w for w in re.split(r"\W+", desc) if w not in STOPWORDS}
        
        score = len(intent_words.intersection(name_words)) * 2 + len(intent_words.intersection(desc_words))
        if score > 0:
            ranked.append((score, skill))

    # Sort descending by score
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in ranked]
