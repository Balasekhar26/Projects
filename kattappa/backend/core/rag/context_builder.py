from backend.core.memory.memory_store import MemoryStore

class RAGContextBuilder:
    @staticmethod
    def build_context(
        retrieved_ranks: list[tuple[str, float]], 
        max_tokens: int = 4000
    ) -> str:
        """Loads actual chunk text from the DB, budget-checks, formats context, and logs stats."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        
        context_blocks = []
        accumulated_tokens = 0
        
        for chunk_id, score in retrieved_ranks:
            cursor.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            if not row:
                continue
                
            chunk = dict(row)
            chunk_text = chunk["text"]
            token_count = chunk["token_count"]
            
            if accumulated_tokens + token_count > max_tokens:
                # Log stats with success=False if skipped due to budget limits
                MemoryStore.log_retrieval_stat(chunk_id=chunk_id, score=score, success=False)
                continue
                
            # Fetch document title
            cursor.execute("SELECT title FROM documents WHERE doc_id = ?", (chunk["doc_id"],))
            doc_row = cursor.fetchone()
            doc_title = doc_row["title"] if doc_row else "Unknown Source"
            
            block = f"[Source: {doc_title}] (Relevance Score: {score:.4f})\n{chunk_text}\n"
            context_blocks.append(block)
            accumulated_tokens += token_count
            
            # Log successful retrieval stats
            MemoryStore.log_retrieval_stat(chunk_id=chunk_id, score=score, success=True)
            
        if not context_blocks:
            return ""
            
        return "\n=== RETRIEVED KNOWLEDGE SOURCE ===\n" + "\n".join(context_blocks) + "==================================\n"
