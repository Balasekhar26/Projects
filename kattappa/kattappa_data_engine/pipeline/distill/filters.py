import re
from typing import List, Dict, Any

class QualityControlLayer:
    def __init__(self, min_composite_score: float = 7.0, similarity_threshold: float = 0.95):
        self.min_composite_score = min_composite_score
        self.similarity_threshold = similarity_threshold
        self.seen_texts = {} # grouped by category to avoid unnecessary cross-checks

    def passes_hard_filters(self, node: Dict[str, Any]) -> bool:
        """Verifies candidate matches composite score and structural boundaries."""
        # 1. Hard Floor Reject
        if node["composite_score"] < self.min_composite_score:
            return False
            
        # 2. Structural checks (reject truncated or empty answers)
        text = node["final_response"].strip()
        if not text or len(text) < 50:
            return False
            
        return True

    def passes_novelty_filter(self, node: Dict[str, Any]) -> bool:
        """Calculates cosine similarity to prevent redundant semantic duplicates."""
        cat = node["category"]
        text = node["final_response"]
        
        if cat not in self.seen_texts:
            self.seen_texts[cat] = []
            
        if not self.seen_texts[cat]:
            self.seen_texts[cat].append(text)
            return True
            
        # Extract features using TfidfVectorizer
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            
            corpus = self.seen_texts[cat] + [text]
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf = vectorizer.fit_transform(corpus)
            
            # Compare final document against prior elements
            sim = cosine_similarity(tfidf[-1], tfidf[:-1])
            max_sim = sim.max()
            
            if max_sim > self.similarity_threshold:
                # Discard duplicate
                return False
                
            self.seen_texts[cat].append(text)
            return True
        except ImportError:
            # Fallback helper if sklearn is not loaded
            # Standard exact substring deduplication
            for prior in self.seen_texts[cat]:
                if prior[:200] == text[:200]:
                    return False
            self.seen_texts[cat].append(text)
            return True

    def calculate_diversity_score(self, batch: List[Dict[str, Any]]) -> Dict[str, float]:
        """Analyzes sentence length distributions and lexical variety across batch."""
        if not batch:
            return {"avg_word_count": 0.0, "lexical_diversity": 0.0}
            
        total_words = 0
        all_words = []
        
        for item in batch:
            text = item["final_response"]
            words = re.findall(r"\w+", text.lower())
            total_words += len(words)
            all_words.extend(words)
            
        unique_words = len(set(all_words))
        lexical_div = unique_words / len(all_words) if all_words else 0.0
        
        return {
            "avg_word_count": round(total_words / len(batch), 2),
            "lexical_diversity": round(lexical_div, 4)
        }
