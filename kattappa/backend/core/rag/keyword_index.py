import math
import re

class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avg_doc_len = 0.0
        self.doc_lens = {}
        self.doc_freqs = {}
        self.idf = {}
        self.documents = {}

    def tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def index_chunks(self, chunks: list[dict]) -> None:
        """Indexes doc chunks to compute tf, idf, and average doc lengths."""
        self.documents = {}
        self.doc_lens = {}
        self.doc_freqs = {}
        self.corpus_size = len(chunks)
        
        if self.corpus_size == 0:
            return
            
        total_len = 0
        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            text = chunk["text"]
            words = self.tokenize(text)
            self.documents[chunk_id] = words
            self.doc_lens[chunk_id] = len(words)
            total_len += len(words)
            
            # Record unique word occurrences in chunk
            unique_words = set(words)
            for word in unique_words:
                self.doc_freqs[word] = self.doc_freqs.get(word, 0) + 1
                
        self.avg_doc_len = total_len / self.corpus_size
        
        # Calculate IDF
        self.idf = {}
        for word, freq in self.doc_freqs.items():
            self.idf[word] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Calculates BM25 relevance scores for the query terms against all chunks."""
        query_words = self.tokenize(query)
        scores = {}
        
        for chunk_id, doc_words in self.documents.items():
            doc_len = self.doc_lens[chunk_id]
            score = 0.0
            word_counts = {}
            for w in doc_words:
                word_counts[w] = word_counts.get(w, 0) + 1
                
            for q_word in query_words:
                if q_word in word_counts:
                    tf = word_counts[q_word]
                    idf_val = self.idf.get(q_word, 0.0)
                    
                    # BM25 TF formula
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0)))
                    score += idf_val * (numerator / denominator)
            if score > 0.0:
                scores[chunk_id] = score
                
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]
