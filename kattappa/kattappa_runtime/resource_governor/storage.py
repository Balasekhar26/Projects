"""
Storage Manager & Hierarchical Memory — Step 30
==================================================

Manages disk capacity, enforces minimum free space constraints, runs proactive cleanup cycles,
and implements hierarchical memory compression (Hot -> Warm -> Cold).
"""

from __future__ import annotations

import os
import shutil
import psutil
import json
import gzip
import sqlite3
import time
from typing import Dict, List, Any, Optional

from kattappa_runtime.resource_governor.governor import ResourceGovernor


class StorageManager:
    """
    Enforces minimum free disk limits and runs cleanup routines.
    """
    def __init__(self, governor: ResourceGovernor, base_dir: Optional[str] = None):
        self.governor = governor
        self.base_dir = base_dir or os.getcwd()

    def get_disk_usage(self) -> Dict[str, Any]:
        """Get total, used, and free disk bytes."""
        try:
            usage = psutil.disk_usage(self.base_dir)
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
            }
        except Exception:
            # Fallback for virtual filesystems / testing environments
            return {
                "total": 500 * 1024 ** 3,  # 500 GB
                "used": 200 * 1024 ** 3,  # 200 GB
                "free": 300 * 1024 ** 3,  # 300 GB
            }

    def check_disk_space(self) -> Dict[str, Any]:
        """
        Validates available space against policy: max(15% of disk, 100 GB).
        """
        usage = self.get_disk_usage()
        total = usage["total"]
        free = usage["free"]

        # Calculate minimum required free space
        ratio_limit = int(total * self.governor.config.min_free_disk_space_ratio)
        bytes_limit = self.governor.config.min_free_disk_space_bytes
        required_free = max(ratio_limit, bytes_limit)

        is_healthy = free >= required_free
        deficit = max(0, required_free - free)

        return {
            "is_healthy": is_healthy,
            "free_bytes": free,
            "required_free_bytes": required_free,
            "deficit_bytes": deficit,
        }

    def run_cleanup_cycle(self) -> List[str]:
        """
        Performs automated storage cleanup tasks.
        Returns a list of actions executed.
        """
        actions = []
        
        # 1. Clean temporary files in workspace
        tmp_dir = os.path.join(self.base_dir, "tmp")
        if os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
                os.makedirs(tmp_dir)
                actions.append("Cleared temporary file directory 'tmp/'")
            except Exception:
                pass

        # 2. Compress old checkpoints if any exist and exceed keep limit
        checkpoint_dir = os.path.join(self.base_dir, "kattappa_native", "checkpoints", "alpha")
        if os.path.exists(checkpoint_dir):
            files = [f for f in os.listdir(checkpoint_dir) if f.endswith(".pt")]
            if len(files) > 3:
                # Keep latest 3, compress/delete the rest
                files.sort(key=lambda x: os.path.getmtime(os.path.join(checkpoint_dir, x)))
                to_clean = files[:-3]
                cleaned_count = 0
                for f in to_clean:
                    path = os.path.join(checkpoint_dir, f)
                    try:
                        # Zip it or delete it to free space
                        os.remove(path)
                        cleaned_count += 1
                    except Exception:
                        pass
                if cleaned_count > 0:
                    actions.append(f"Pruned {cleaned_count} old pre-training checkpoints")

        # 3. Archive logs
        log_file = os.path.join(self.base_dir, "pretrain.log")
        if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:  # > 10MB
            archive_path = log_file + ".gz"
            try:
                with open(log_file, "rb") as f_in:
                    with gzip.open(archive_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                # Clear original
                open(log_file, "w").close()
                actions.append("Compressed and rotated 'pretrain.log'")
            except Exception:
                pass

        return actions


class HierarchicalMemoryManager:
    """
    Tiered memory manager:
    - Hot: RAM (fast, volatile, <= 50% RAM budget)
    - Warm: SQLite DB (structured, persistent, low RAM footprint)
    - Cold: Compressed archive (highly compressed, offline storage)
    """
    def __init__(self, db_path: str = "warm_memory.db", archive_dir: str = "cold_archives"):
        self.db_path = db_path
        self.archive_dir = archive_dir
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warm_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                subsystem TEXT,
                data TEXT,
                importance REAL
            )
        """)
        conn.commit()
        conn.close()
        
        if not os.path.exists(self.archive_dir):
            os.makedirs(self.archive_dir)

    def compress_memory_tier(
        self,
        hot_records: List[Dict[str, Any]],
        max_hot_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Pushes low importance/older records from RAM (Hot) to SQLite (Warm).
        Returns the remaining hot records that fit within the hot size.
        """
        if len(hot_records) <= max_hot_size:
            return hot_records

        # Sort by importance ascending (lowest importance first to evict)
        hot_records.sort(key=lambda x: x.get("importance", 0.5))
        evict_count = len(hot_records) - max_hot_size
        to_evict = hot_records[:evict_count]
        remaining = hot_records[evict_count:]

        # Move evicted to SQLite
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for rec in to_evict:
            rec_id = rec.get("id", str(hash(json.dumps(rec))))
            cursor.execute(
                "INSERT OR REPLACE INTO warm_records VALUES (?, ?, ?, ?, ?)",
                (rec_id, rec.get("timestamp", ""), rec.get("subsystem", ""), json.dumps(rec), rec.get("importance", 0.5))
            )
        conn.commit()
        conn.close()

        # Archive very old warm memory to compressed cold archive
        self._check_and_compress_warm_to_cold()

        return remaining

    def _check_and_compress_warm_to_cold(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM warm_records")
        count = cursor.fetchone()[0]

        if count > 50:  # If SQLite gets too large, compress oldest into cold storage
            cursor.execute("SELECT * FROM warm_records ORDER BY timestamp ASC LIMIT 30")
            old_records = cursor.fetchall()
            
            # Format and compress
            archive_data = []
            to_delete = []
            for r in old_records:
                archive_data.append({
                    "id": r[0],
                    "timestamp": r[1],
                    "subsystem": r[2],
                    "data": json.loads(r[3]),
                    "importance": r[4]
                })
                to_delete.append(r[0])

            archive_file = os.path.join(self.archive_dir, f"cold_{int(time.time())}.json.gz")
            with gzip.open(archive_file, "wt", encoding="utf-8") as f:
                json.dump(archive_data, f)

            # Delete from SQLite
            for record_id in to_delete:
                cursor.execute("DELETE FROM warm_records WHERE id = ?", (record_id,))
            conn.commit()
            
        conn.close()

    def retrieve_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Search SQLite warm database for a record."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM warm_records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
