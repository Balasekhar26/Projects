from __future__ import annotations
import sqlite3
import time
import contextlib
from typing import Any
from backend.knowledge_graph.graph_store import GraphStore

class TemporalDecayEngine:
    """Computes expected decay factors and decays fact confidence values over time."""

    def __init__(self, store: GraphStore = None) -> None:
        self.store = store or GraphStore()

    def apply_decay(self, decay_rate_per_day: float = 0.05) -> None:
        """Decays the confidence scores of facts based on elapsed time."""
        with contextlib.closing(sqlite3.connect(self.store.db_path)) as conn:
            now_ts = time.time()
            # Load active facts
            rows = conn.execute("SELECT id, confidence, timestamp FROM triples WHERE status = 'ACTIVE'").fetchall()
            for row in rows:
                row_id, old_conf, timestamp = row
                elapsed_days = (now_ts - timestamp) / (24 * 3600)
                
                # Apply linear decay bounds
                decay = elapsed_days * decay_rate_per_day
                new_conf = max(0.1, old_conf - decay)
                
                # Update confidence parameters in db
                conn.execute(
                    "UPDATE triples SET confidence = ?, timestamp = ? WHERE id = ?",
                    (new_conf, now_ts, row_id)
                )
            conn.commit()
