import uuid
from datetime import datetime
from backend.core.memory.memory_store import MemoryStore

class EpisodeStore:
    def __init__(self):
        # Create episodic tables if they don't already exist
        conn = MemoryStore._get_conn()
        with MemoryStore._lock:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_episodes (
                    id TEXT PRIMARY KEY,
                    goal TEXT,
                    result TEXT,
                    failure_reason TEXT,
                    created_at TEXT
                )
            """)
            conn.commit()

    def save_episode(self, goal: str, result: str, failure_reason: str) -> None:
        """Saves a structured execution episode to database logs."""
        conn = MemoryStore._get_conn()
        now = datetime.now().isoformat()
        episode_id = f"ep_{uuid.uuid4()}"
        
        with MemoryStore._lock:
            conn.execute("""
                INSERT INTO episodic_episodes (id, goal, result, failure_reason, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (episode_id, goal, result, failure_reason, now))
            conn.commit()

    def get_all_episodes(self) -> list[dict]:
        """Retrieves all historical episodes stored in memory."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        
        with MemoryStore._lock:
            cursor.execute("SELECT * FROM episodic_episodes ORDER BY created_at DESC")
            rows = cursor.fetchall()
            
        return [
            {
                "id": r["id"],
                "goal": r["goal"],
                "result": r["result"],
                "failure_reason": r["failure_reason"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]
