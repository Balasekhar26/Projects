from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class CurriculumEngine:
    """Curriculum Engine Subsystem (Layer 8 - Step 8.5).

    Schedules learning challenges for self-improvement and evaluates agent capabilities
    against custom criteria to prioritize target training workloads.
    """

    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_curriculum_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL, -- 'coding', 'memory', 'safety', 'tools', 'speed'
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    success_criteria TEXT NOT NULL DEFAULT '{}', -- JSON criteria (e.g. {"min_success_rate": 0.8})
                    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'active', 'passed', 'failed'
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_curriculum_status ON hm_curriculum_challenges(status);
                CREATE INDEX IF NOT EXISTS idx_curriculum_category ON hm_curriculum_challenges(category);
                """
            )
            conn.commit()

    @classmethod
    def add_challenge(
        cls,
        challenge_id: str,
        category: str,
        title: str,
        description: str,
        success_criteria: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registers a new learning challenge in the curriculum ledger."""
        criteria = success_criteria or {}
        criteria_str = json.dumps(criteria)
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_curriculum_challenges (challenge_id, category, title, description, success_criteria, status, attempts)
                    VALUES (?, ?, ?, ?, ?, 'pending', 0)
                    ON CONFLICT(challenge_id) DO UPDATE SET
                        category = excluded.category,
                        title = excluded.title,
                        description = excluded.description,
                        success_criteria = excluded.success_criteria
                    """,
                    (challenge_id.strip(), category.strip().lower(), title.strip(), description.strip(), criteria_str)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def list_challenges(cls, category: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns registered challenges, filtered by category or status."""
        conn = cls._get_sqlite_conn()
        try:
            query = "SELECT * FROM hm_curriculum_challenges WHERE 1=1"
            params = []
            if category:
                query += " AND category = ?"
                params.append(category.lower().strip())
            if status:
                query += " AND status = ?"
                params.append(status.lower().strip())

            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                results.append({
                    "challenge_id": r["challenge_id"],
                    "category": r["category"],
                    "title": r["title"],
                    "description": r["description"],
                    "success_criteria": json.loads(r["success_criteria"]),
                    "status": r["status"],
                    "attempts": r["attempts"],
                    "last_attempt_at": r["last_attempt_at"],
                })
            return results
        finally:
            conn.close()

    @classmethod
    def update_challenge_attempt(cls, challenge_id: str, run_success: bool, metrics: Dict[str, Any]) -> str:
        """Logs an execution attempt for a challenge, evaluates its success criteria, and updates status."""
        now = time.time()
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                row = conn.execute("SELECT * FROM hm_curriculum_challenges WHERE challenge_id = ?", (challenge_id,)).fetchone()
                if not row:
                    raise ValueError(f"Challenge '{challenge_id}' not found.")

                criteria = json.loads(row["success_criteria"])
                attempts = row["attempts"] + 1

                # Evaluate criteria
                passed = True
                if not run_success:
                    passed = False

                min_success_rate = criteria.get("min_success_rate")
                if min_success_rate is not None:
                    actual_rate = metrics.get("success_rate", 0.0)
                    if actual_rate < min_success_rate:
                        passed = False

                max_duration_ms = criteria.get("max_duration_ms")
                if max_duration_ms is not None:
                    actual_duration = metrics.get("duration_ms", 0)
                    if actual_duration > max_duration_ms:
                        passed = False

                status = "passed" if passed else "failed"

                conn.execute(
                    """
                    UPDATE hm_curriculum_challenges
                    SET status = ?, attempts = ?, last_attempt_at = ?
                    WHERE challenge_id = ?
                    """,
                    (status, attempts, now, challenge_id)
                )
                conn.commit()
                log_event("curriculum_challenge", {"challenge_id": challenge_id, "status": status, "attempts": attempts})
                return status
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def get_recommended_challenges(cls) -> List[Dict[str, Any]]:
        """Identifies agent execution bottlenecks and recommends corresponding learning challenges."""
        # Find lowest success agent category
        lowest_agent = None
        lowest_success = 1.0

        try:
            from backend.core.action_memory import ActionMemory
            agents = ["browser", "researcher", "coder", "file", "desktop", "voice", "terminal"]
            for agent in agents:
                stats = ActionMemory.get_agent_statistics(agent).to_dict()
                total = stats.get("total_actions", 0)
                if total > 0:
                    rate = stats.get("success_rate", 1.0)
                    if rate < lowest_success:
                        lowest_success = rate
                        lowest_agent = agent
        except Exception:
            pass

        # Map agent name to category
        category_map = {
            "coder": "coding",
            "researcher": "memory",
            "browser": "tools",
            "desktop": "tools",
            "terminal": "tools",
        }
        target_category = category_map.get(lowest_agent) if lowest_agent else None

        challenges = []
        if target_category:
            # First look for pending or failed challenges in target category
            challenges = cls.list_challenges(category=target_category, status="pending")
            if not challenges:
                challenges = cls.list_challenges(category=target_category, status="failed")

        # Fallback to any pending challenges
        if not challenges:
            challenges = cls.list_challenges(status="pending")

        # Secondary fallback to any failed challenges
        if not challenges:
            challenges = cls.list_challenges(status="failed")

        return challenges

    @classmethod
    def diagnose_and_generate_curriculum(cls) -> Dict[str, Any]:
        """Scans AgentReputationTracker, detects low performing agents, and generates a structured learning curriculum (K27)."""
        lowest_agent = None
        lowest_score = 1.0
        
        try:
            from backend.core.agent_reputation import AgentReputationTracker
            agents = ["planner", "coder", "browser", "desktop", "researcher", "voice", "vision"]
            for agent in agents:
                rep = AgentReputationTracker.get_reputation(agent)
                if rep and rep.get("success_rate", 1.0) < lowest_score:
                    lowest_score = rep["success_rate"]
                    lowest_agent = agent
        except Exception:
            pass

        # If no real data, fallback or simulate based on early mature layers
        if not lowest_agent or lowest_score >= 0.90:
            lowest_agent = "desktop"
            lowest_score = 0.75

        # Define curriculums mapping for each weak agent type
        curriculums = {
            "coder": {
                "goal": "Improve automated software refactoring",
                "weakness": "Exception safety & type checking constraints",
                "steps": [
                    "Exception safety guarantees in Python",
                    "Static type checking with mypy & annotations",
                    "Unit test boundary condition validation",
                    "Design pattern alignment and decoupling",
                    "Refactoring legacy spaghetti code labs"
                ]
            },
            "browser": {
                "goal": "Improve web scrapers and form filling",
                "weakness": "Handling dynamic DOM and anti-bot overlays",
                "steps": [
                    "Dynamic DOM navigation & element queries",
                    "Vapor-state element handling under timeout",
                    "Simulating authentic user scroll & clicks",
                    "Overcoming captchas & cookie approval overlays",
                    "Practical form auto-filling labs"
                ]
            },
            "desktop": {
                "goal": "Improve OS automation precision",
                "weakness": "Coordinates misalignment & window focus delays",
                "steps": [
                    "OS window focus & state detection",
                    "Dynamic screen coordinates alignment",
                    "Keyboard & mouse timing synchronization",
                    "Handling dialog modal popups cleanly",
                    "Automated folder organization labs"
                ]
            },
            "researcher": {
                "goal": "Improve facts extraction from long papers",
                "weakness": "Hallucination under dense mathematical contexts",
                "steps": [
                    "Identifying research publication structures",
                    "Mathematical equations translation to algorithms",
                    "Cross-reference source truth validation",
                    "Episodic recall context ranking",
                    "Research abstract summarization labs"
                ]
            },
            "voice": {
                "goal": "Improve natural language Telugu speech",
                "weakness": "Acoustic noise & accent variations filtering",
                "steps": [
                    "Telugu acoustic phonetics and accents",
                    "Local background noise attenuation",
                    "Dialogue turn-taking time threshold alignment",
                    "Emotion layer response planner mapping",
                    "Telugu voice conversation labs"
                ]
            }
        }

        curr = curriculums.get(lowest_agent, {
            "goal": f"Improve {lowest_agent} specialism",
            "weakness": "Instruction parsing ambiguity",
            "steps": [
                "Instruction parsing patterns",
                "Context parsing disambiguation",
                "Action sequence composition",
                "Error boundary handling",
                "Specialist capability validation labs"
            ]
        })

        # Register challenges in database
        challenge_prefix = f"CURR_{lowest_agent.upper()}"
        for idx, step in enumerate(curr["steps"]):
            challenge_id = f"{challenge_prefix}_STEP_{idx+1}"
            cls.add_challenge(
                challenge_id=challenge_id,
                category="coding" if lowest_agent == "coder" else "tools",
                title=f"{curr['goal']}: {step}",
                description=f"Curriculum step for resolving weakness: {curr['weakness']}.",
                success_criteria={"min_success_rate": 0.85}
            )

        return {
            "detected_weakness_agent": lowest_agent,
            "success_score": lowest_score,
            "goal": curr["goal"],
            "detected_weakness": curr["weakness"],
            "curriculum_steps": curr["steps"]
        }
