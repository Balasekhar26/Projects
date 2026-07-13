from __future__ import annotations
import sqlite3
import os
import time
import contextlib
from typing import Any, Dict, List, Optional
from backend.knowledge_graph.triple import Triple

class GraphStore:
    """Manages the persistent semantic graph store and handles contradictions."""

    def __init__(self, db_path: str = "backend/data/knowledge_graph.db") -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._setup_schema()

    def _setup_schema(self) -> None:
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS triples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp REAL NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT DEFAULT 'ACTIVE'
                )
            """)
            conn.commit()

    def add_triple(self, triple: Triple) -> None:
        """Adds a triple to the graph, automatically resolving conflicts."""
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            # 1. Check for contradictions: same subject + predicate, but different object
            conflicting = conn.execute(
                "SELECT id, object, confidence FROM triples WHERE subject = ? AND predicate = ? AND status = 'ACTIVE'",
                (triple.subject, triple.predicate)
            ).fetchall()

            for row in conflicting:
                row_id, old_obj, old_conf = row
                if old_obj != triple.object:
                    # Contradiction detected
                    if triple.confidence >= old_conf:
                        # Demote existing fact to historical
                        conn.execute("UPDATE triples SET status = 'HISTORICAL' WHERE id = ?", (row_id,))
                    else:
                        # Ignore or demote new incoming fact
                        conn.execute(
                            "INSERT INTO triples (subject, predicate, object, confidence, timestamp, source, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (triple.subject, triple.predicate, triple.object, triple.confidence, triple.timestamp, triple.source, 'HISTORICAL')
                        )
                        conn.commit()
                        return

            # Insert new active fact
            conn.execute(
                "INSERT INTO triples (subject, predicate, object, confidence, timestamp, source, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (triple.subject, triple.predicate, triple.object, triple.confidence, triple.timestamp, triple.source, 'ACTIVE')
            )
            conn.commit()

    def get_triples(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        status: str = 'ACTIVE'
    ) -> List[Triple]:
        """Queries matching active semantic triples from storage."""
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            query = "SELECT subject, predicate, object, confidence, timestamp, source FROM triples WHERE status = ?"
            params: List[Any] = [status]

            if subject:
                query += " AND subject = ?"
                params.append(subject)
            if predicate:
                query += " AND predicate = ?"
                params.append(predicate)
            if obj:
                query += " AND object = ?"
                params.append(obj)

            rows = conn.execute(query, params).fetchall()
            return [Triple(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]
