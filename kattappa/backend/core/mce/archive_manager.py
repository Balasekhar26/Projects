"""MCE Component 6: Archive Manager.

Marks stale low-recall episodes as ARCHIVED in the episodic store.
Never deletes records — preserves full audit trails.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass

from backend.core.config import load_config
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class ArchiveReport:
    archived_count: int = 0
    total_scanned: int = 0
    skipped_pinned: int = 0


class MCEArchiveManager:
    """Archives stale episodic memories that have low recall and are older than threshold."""

    DEFAULT_ARCHIVE_AFTER_DAYS: float = 30.0
    DEFAULT_MAX_RECALL_TO_ARCHIVE: int = 1   # episodes with ≤ 1 recall are archivable

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @classmethod
    def archive_stale(
        cls,
        archive_after_days: float = DEFAULT_ARCHIVE_AFTER_DAYS,
        max_recall_count: int = DEFAULT_MAX_RECALL_TO_ARCHIVE,
    ) -> ArchiveReport:
        """Marks old low-recall episodes as ARCHIVED."""
        report = ArchiveReport()
        cutoff = time.time() - (archive_after_days * 86400.0)

        conn = cls._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT id, pinned, recall_count FROM hm_episodes
                WHERE created_at < ? AND recall_count <= ?
                """,
                (cutoff, max_recall_count),
            ).fetchall()
            report.total_scanned = len(rows)

            ids_to_archive = []
            for row in rows:
                if int(row["pinned"]) == 1:
                    report.skipped_pinned += 1
                    continue
                ids_to_archive.append(row["id"])

            if ids_to_archive:
                import json
                for ep_id in ids_to_archive:
                    # Add 'archived' tag to the episode
                    tag_row = conn.execute(
                        "SELECT tags FROM hm_episodes WHERE id = ?", (ep_id,)
                    ).fetchone()
                    if tag_row:
                        try:
                            tags = json.loads(tag_row["tags"])
                        except Exception:
                            tags = []
                        if "archived" not in tags:
                            tags.append("archived")
                        conn.execute(
                            "UPDATE hm_episodes SET tags = ? WHERE id = ?",
                            (json.dumps(tags), ep_id),
                        )
                conn.commit()
                report.archived_count = len(ids_to_archive)

        except Exception as exc:
            logger.error("ArchiveManager error: %s", exc)
            conn.rollback()
        finally:
            conn.close()

        log_event(
            "mce_archive_complete",
            f"Archive complete: archived={report.archived_count}, "
            f"scanned={report.total_scanned}, pinned_skipped={report.skipped_pinned}",
        )
        return report
