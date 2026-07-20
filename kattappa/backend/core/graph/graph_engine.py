import re
import uuid
from backend.core.memory.memory_store import MemoryStore
from backend.core.graph.graph_extractor import GraphExtractor
from backend.core.graph.graph_retriever import GraphRetriever

class GraphEngine:
    @classmethod
    def index_chunk(cls, chunk_id: str, text: str) -> None:
        """Parses chunk content, registers extracted entities/mentions, and stores relationship chains."""
        relations = GraphExtractor.extract_relations(text, chunk_id)
        
        # Simple sentence boundaries to capture context
        sentences = re.split(r'\.|\?|\!', text)
        
        for rel in relations:
            # 1. Upsert source and target entities
            MemoryStore.upsert_entity(
                entity_id=rel["source_id"],
                name=rel["source_name"],
                entity_type="concept"
            )
            MemoryStore.upsert_entity(
                entity_id=rel["target_id"],
                name=rel["target_name"],
                entity_type="concept"
            )
            
            # 2. Add relationship chain
            MemoryStore.add_graph_relationship(
                rel_id=rel["relationship_id"],
                source_id=rel["source_id"],
                target_id=rel["target_id"],
                predicate=rel["predicate"],
                metadata={"confidence": rel["confidence"]},
                source_chunk_id=rel["source_chunk_id"],
                extraction_method=rel["extraction_method"]
            )
            
            # 3. Find matching sentence context for mentions
            sentence_context = ""
            for sentence in sentences:
                if rel["source_name"] in sentence and rel["target_name"] in sentence:
                    sentence_context = sentence.strip()
                    break
                    
            if not sentence_context and sentences:
                sentence_context = sentences[0].strip()
                
            # 4. Add entity mentions mapping
            MemoryStore.add_entity_mention(
                mention_id=str(uuid.uuid4()),
                entity_id=rel["source_id"],
                chunk_id=chunk_id,
                sentence_context=sentence_context
            )
            MemoryStore.add_entity_mention(
                mention_id=str(uuid.uuid4()),
                entity_id=rel["target_id"],
                chunk_id=chunk_id,
                sentence_context=sentence_context
            )

    @classmethod
    def query(cls, query_text: str, max_depth: int = 3) -> str:
        """Traverses the semantic entities graph matching terms inside query_text."""
        return GraphRetriever.query_graph(query_text, max_depth=max_depth)
