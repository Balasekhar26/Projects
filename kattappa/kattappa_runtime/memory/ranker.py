import time
import math
from typing import List, Dict, Any

class MemoryRanker:
    def __init__(self, decay_constant_lambda: float = 0.0001):
        # Time decay lambda (default: decays exponentially over seconds/hours)
        self.decay_lambda = decay_constant_lambda

    def rank_memories(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Applies triple weighted equation scoring to sort relevant memory records."""
        if not candidates:
            return []

        # 1. Compute Relevance (TF-IDF Cosine Similarity)
        relevance_scores = self._compute_relevance(query, candidates)

        ranked = []
        current_time = int(time.time())

        for idx, item in enumerate(candidates):
            relevance = relevance_scores[idx]
            importance = item.get("importance") or item.get("confidence", 0.5)
            
            # Recency Calculation: e^(-lambda * delta_t)
            unix_time = item.get("unix_time", current_time)
            delta_t = max(0, current_time - unix_time)
            recency = math.exp(-self.decay_lambda * delta_t)

            # Combined weighted score
            score = 0.5 * relevance + 0.3 * importance + 0.2 * recency
            
            # Format text representation depending on schema category
            if "event" in item:
                ts = item.get("timestamp", "unknown time")
                text_repr = f"[Event at {ts}] {item['event']}"
            else:
                subj = item.get("subject", "general")
                rel = item.get("relation", "info")
                f = item.get("fact", "")
                text_repr = f"[Fact: {subj} {rel} -> {f}]"

            ranked.append({
                "candidate": item,
                "text": text_repr,
                "relevance": round(relevance, 4),
                "recency": round(recency, 4),
                "importance": round(importance, 4),
                "score": round(score, 4)
            })

        # Sort descending by score
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    def _compute_relevance(self, query: str, candidates: List[Dict[str, Any]]) -> List[float]:
        """Calculates cosine similarity vectors between query and item texts."""
        texts = []
        for item in candidates:
            if "event" in item:
                texts.append(item["event"])
            else:
                texts.append(f"{item['subject']} {item['relation']} {item['fact']}")

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            corpus = texts + [query]
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf = vectorizer.fit_transform(corpus)
            
            # Compare last vector (query) with preceding candidate vectors
            sims = cosine_similarity(tfidf[-1], tfidf[:-1])[0]
            return list(sims)
        except Exception:
            # Fallback simple keyword overlap ratio if sklearn has issues
            scores = []
            q_words = set(query.lower().split())
            for t in texts:
                t_words = set(t.lower().split())
                if not q_words:
                    scores.append(0.0)
                else:
                    scores.append(len(q_words.intersection(t_words)) / len(q_words))
            return scores
