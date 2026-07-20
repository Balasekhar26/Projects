from backend.core.memory.memory_store import MemoryStore

class SemanticStore:
    def __init__(self):
        # Initialise semantic table if not exists
        conn = MemoryStore._get_conn()
        with MemoryStore._lock:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_facts (
                    concept_id TEXT,
                    predicate TEXT,
                    target_id TEXT,
                    confidence REAL,
                    PRIMARY KEY (concept_id, predicate, target_id)
                )
            """)
            conn.commit()

    def save_fact(self, concept_id: str, predicate: str, target_id: str, confidence: float) -> None:
        """Saves or updates a fact relationship in the semantic memory database."""
        conn = MemoryStore._get_conn()
        with MemoryStore._lock:
            conn.execute("""
                INSERT INTO semantic_facts (concept_id, predicate, target_id, confidence)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(concept_id, predicate, target_id) DO UPDATE SET
                    confidence = excluded.confidence
            """, (concept_id, predicate, target_id, confidence))
            conn.commit()

    def get_fact(self, concept_id: str, predicate: str, target_id: str) -> dict | None:
        """Retrieves a specific fact relationship from the database."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        
        with MemoryStore._lock:
            cursor.execute("""
                SELECT * FROM semantic_facts 
                WHERE concept_id = ? AND predicate = ? AND target_id = ?
            """, (concept_id, predicate, target_id))
            row = cursor.fetchone()
            
        if row:
            return {
                "concept_id": row["concept_id"],
                "predicate": row["predicate"],
                "target_id": row["target_id"],
                "confidence": row["confidence"]
            }
        return None
