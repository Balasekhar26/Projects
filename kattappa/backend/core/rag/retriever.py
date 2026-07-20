class Retriever:
    @staticmethod
    def fuse_rankings(
        keyword_results: list[tuple[str, float]], 
        vector_results: list[tuple[str, float]], 
        k: int = 60,
        top_k: int = 10
    ) -> list[tuple[str, float]]:
        """Applies Reciprocal Rank Fusion (RRF) on keyword and vector results."""
        rrf_scores = {}
        
        # Helper to apply RRF points
        def apply_ranks(results):
            for rank, (chunk_id, _) in enumerate(results, start=1):
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
                
        apply_ranks(keyword_results)
        apply_ranks(vector_results)
        
        # Apply time-decayed feedback penalties
        from backend.core.rag.adaptive_feedback import AdaptiveFeedback
        penalties = AdaptiveFeedback.get_chunk_penalties()
        
        for chunk_id in rrf_scores:
            if chunk_id in penalties:
                rrf_scores[chunk_id] -= penalties[chunk_id]
                
        sorted_fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_fused[:top_k]
