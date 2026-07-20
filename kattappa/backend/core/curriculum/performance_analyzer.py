from backend.core.memory.memory_store import MemoryStore

class PerformanceAnalyzer:
    @classmethod
    def identify_weak_skills(cls, failure_threshold: float = 0.15) -> list[str]:
        """Queries SQLite task execution outcomes and lists skill IDs with failure rates >= threshold."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        
        with MemoryStore._lock:
            cursor.execute("""
                SELECT task_id, COUNT(*) as total, SUM(success) as successful 
                FROM execution_outcomes 
                GROUP BY task_id
            """)
            rows = cursor.fetchall()
            
        weak_skills = []
        for r in rows:
            total = float(r["total"])
            successful = float(r["successful"] or 0)
            failure_rate = 1.0 - (successful / total)
            
            if failure_rate >= failure_threshold:
                weak_skills.append(r["task_id"])
                
        return weak_skills
