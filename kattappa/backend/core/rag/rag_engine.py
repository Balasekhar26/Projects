import uuid
from backend.core.memory.memory_store import MemoryStore
from backend.core.rag.document_loader import DocumentLoader
from backend.core.rag.chunker import Chunker
from backend.core.rag.embedding_engine import EmbeddingEngine
from backend.core.rag.vector_store import VectorStore
from backend.core.rag.keyword_index import BM25Index
from backend.core.rag.retriever import Retriever
from backend.core.rag.context_builder import RAGContextBuilder

class RAGEngine:
    _vector_store = VectorStore()
    _bm25_index = BM25Index()

    @classmethod
    def index_document(cls, doc_id: str, title: str, source: str, file_path: str) -> None:
        """Loads, chunks, stores doc chunks in SQLite, and rebuilds retrieval indexes."""
        text = DocumentLoader.load_file(file_path)
        chunks = Chunker.chunk_text(text)
        
        MemoryStore.add_document(doc_id=doc_id, title=title, source=source)
        
        for chunk in chunks:
            chunk_id = f"chk_{doc_id}_{chunk['chunk_index']}"
            embedding_id = f"emb_{chunk_id}"
            MemoryStore.add_chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                chunk_index=chunk["chunk_index"],
                text=chunk["text"],
                embedding_id=embedding_id,
                token_count=chunk["token_count"]
            )
            
            # Index GraphRAG relations
            from backend.core.graphrag.graph_engine import GraphEngine
            GraphEngine.index_chunk(chunk_id, chunk["text"])
            
        cls.rebuild_indexes()

    @classmethod
    def rebuild_indexes(cls) -> None:
        """Reloads all chunks from SQLite and registers them in vector/BM25 retrievers."""
        cls._vector_store.clear()
        
        all_chunks = MemoryStore.get_all_chunks()
        if not all_chunks:
            return
            
        # Re-index BM25 index
        bm25_chunks = [{"chunk_id": c["chunk_id"], "text": c["text"]} for c in all_chunks]
        cls._bm25_index.index_chunks(bm25_chunks)
        
        # Re-index Vector store
        for c in all_chunks:
            emb = EmbeddingEngine.get_embedding(c["text"])
            cls._vector_store.add_embeddings(c["chunk_id"], emb)

    @classmethod
    def query(cls, query_text: str, top_k: int = 5) -> str:
        """Retrieves and compiles matching context chunks from hybrid keyword/vector search."""
        cls.rebuild_indexes()  # Ensure index is synced with db
        
        # 1. BM25 search
        keyword_res = cls._bm25_index.search(query_text, top_k=20)
        
        # 2. Vector search
        q_emb = EmbeddingEngine.get_embedding(query_text)
        vector_res = cls._vector_store.search(q_emb, top_k=20)
        
        # 3. Reciprocal Rank Fusion (RRF)
        fused = Retriever.fuse_rankings(keyword_res, vector_res, top_k=top_k)
        
        # 4. Build context
        return RAGContextBuilder.build_context(fused)
