from backend.core.memory.memory_store import MemoryStore

class ConfidenceEngine:
    @classmethod
    def calculate_confidence(cls, task_id: str) -> float:
        """Retrieves history metrics from SQLite memory and calculates the expected success probability."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        
        with MemoryStore._lock:
            # Query outcomes
            cursor.execute("""
                SELECT COUNT(*) as total, SUM(success) as successful 
                FROM execution_outcomes 
                WHERE task_id = ?
            """, (task_id,))
            row = cursor.fetchone()
            
        if row and row["total"] > 0:
            total = float(row["total"])
            successful = float(row["successful"] or 0)
            return successful / total
            
        return 0.80 # Baseline confidence score if history is empty
