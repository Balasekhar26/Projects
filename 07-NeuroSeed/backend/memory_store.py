from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SQLITE_PATH = DATA_DIR / "neuroseed_memory.db"
CHROMA_PATH = DATA_DIR / "chroma"
CONSENT_MODEL_VERSION = "pilot-consent-v1"


class NeuroSeedMemoryStore:
    def __init__(self, sqlite_path: Path = SQLITE_PATH) -> None:
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._collection: Any | None = None
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seeds (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    keywords TEXT NOT NULL DEFAULT '[]',
                    cue TEXT NOT NULL DEFAULT '{}',
                    approved INTEGER NOT NULL DEFAULT 0,
                    consent_status TEXT NOT NULL DEFAULT 'pending',
                    consent_model TEXT NOT NULL DEFAULT '',
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    chroma_memory_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consent_logs (
                    id TEXT PRIMARY KEY,
                    seed_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    consent_status TEXT NOT NULL,
                    consent_model TEXT NOT NULL,
                    approved_at TEXT,
                    boundary TEXT NOT NULL DEFAULT '{}',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(seed_id) REFERENCES seeds(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    approved_seed_ids TEXT NOT NULL DEFAULT '[]',
                    cue_events TEXT NOT NULL DEFAULT '[]',
                    uncued_seed_ids TEXT NOT NULL DEFAULT '[]',
                    settings TEXT NOT NULL DEFAULT '{}',
                    safety_boundary TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recall_results (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    session_started_at TEXT,
                    seed_id TEXT NOT NULL,
                    seed_title TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    answer TEXT NOT NULL DEFAULT '',
                    score REAL NOT NULL DEFAULT 0.0,
                    checked_at TEXT NOT NULL,
                    consent_model TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(seed_id) REFERENCES seeds(id)
                )
                """
            )

    def get_state(self) -> dict[str, Any]:
        with sqlite3.connect(self.sqlite_path) as conn:
            seed_rows = conn.execute(
                """
                SELECT id, title, text, keywords, cue, approved, consent_status,
                       consent_model, approved_at, created_at
                FROM seeds
                ORDER BY created_at ASC
                """
            ).fetchall()
            consent_rows = conn.execute(
                """
                SELECT id, seed_id, action, consent_status, consent_model,
                       approved_at, boundary, note, created_at
                FROM consent_logs
                ORDER BY created_at DESC
                LIMIT 200
                """
            ).fetchall()
            session_rows = conn.execute(
                """
                SELECT id, started_at, ended_at, status, approved_seed_ids,
                       cue_events, uncued_seed_ids, settings, safety_boundary
                FROM sessions
                ORDER BY started_at DESC
                LIMIT 100
                """
            ).fetchall()
            recall_rows = conn.execute(
                """
                SELECT id, session_id, session_started_at, seed_id, seed_title,
                       condition, answer, score, checked_at, consent_model
                FROM recall_results
                ORDER BY checked_at DESC
                LIMIT 500
                """
            ).fetchall()

        seeds = [_seed_row(row) for row in seed_rows]
        sessions = [_session_row(row) for row in session_rows]
        recall_results = [_recall_row(row) for row in recall_rows]
        consent_logs = [_consent_row(row) for row in consent_rows]
        cued_ids = sorted({
            str(event.get("seedId") or "")
            for session in sessions
            for event in session.get("cueEvents", [])
            if event.get("seedId")
        })
        return {
            "dataModel": {
                "version": CONSENT_MODEL_VERSION,
                "source": "neuroseed_local_sqlite_chroma",
            },
            "seeds": seeds,
            "logs": _activity_logs(consent_logs, sessions),
            "sessions": sessions,
            "cuedIds": cued_ids,
            "activeSessionId": next(
                (str(session["id"]) for session in sessions if session.get("status") == "running"),
                None,
            ),
            "recallResults": recall_results,
            "consentLogs": consent_logs,
            "summary": _summary(seeds, sessions, recall_results),
        }

    def upsert_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        seeds = _as_list(payload.get("seeds"))
        sessions = _as_list(payload.get("sessions"))
        recall_results = _as_list(payload.get("recallResults"))
        boundary = _as_dict(payload.get("dataModel"))

        with sqlite3.connect(self.sqlite_path) as conn:
            existing = {
                str(row[0]): {
                    "approved": bool(row[1]),
                    "consent_status": str(row[2]),
                    "approved_at": row[3],
                    "chroma_memory_id": str(row[4] or ""),
                }
                for row in conn.execute(
                    """
                    SELECT id, approved, consent_status, approved_at, chroma_memory_id
                    FROM seeds
                    """
                ).fetchall()
            }
            previous_consented_ids = {
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT DISTINCT seed_id
                    FROM consent_logs
                    WHERE consent_status = 'awake-approved'
                    """
                ).fetchall()
            }

        normalized_seeds = [_normalize_seed(seed) for seed in seeds]
        incoming_seed_ids = {str(seed["id"]) for seed in normalized_seeds}
        incoming_session_ids = {
            _clean_str(_as_dict(session).get("id"))
            for session in sessions
            if _clean_str(_as_dict(session).get("id"))
        }
        incoming_recall_ids = {
            _clean_str(_as_dict(result).get("id"))
            for result in recall_results
            if _clean_str(_as_dict(result).get("id"))
        }
        for old_seed_id, old_seed in existing.items():
            if old_seed_id not in incoming_seed_ids:
                self._delete_semantic_seed(old_seed["chroma_memory_id"] or f"neuroseed:{old_seed_id}")

        approved_ids = {
            str(seed["id"])
            for seed in normalized_seeds
            if seed["approved"] and seed["consent"]["status"] == "awake-approved"
        }
        valid_session_seed_ids = approved_ids | previous_consented_ids
        seed_titles = {str(seed["id"]): str(seed["title"]) for seed in normalized_seeds}

        with sqlite3.connect(self.sqlite_path) as conn:
            _delete_rows_not_in(conn, "recall_results", "id", incoming_recall_ids)
            _delete_rows_not_in(conn, "sessions", "id", incoming_session_ids)
            _delete_rows_not_in(conn, "consent_logs", "seed_id", incoming_seed_ids)
            _delete_rows_not_in(conn, "seeds", "id", incoming_seed_ids)

            for seed in normalized_seeds:
                seed_id = str(seed["id"])
                prior = existing.get(seed_id)
                consent = _as_dict(seed["consent"])
                approved = seed_id in approved_ids
                approved_at = consent.get("approvedAt") if approved else None
                memory_id = f"neuroseed:{seed_id}"
                if approved:
                    self._upsert_semantic_seed(memory_id, seed)
                    chroma_memory_id = memory_id
                else:
                    chroma_memory_id = ""
                    old_memory_id = (prior["chroma_memory_id"] if prior else "") or memory_id
                    self._delete_semantic_seed(old_memory_id)

                conn.execute(
                    """
                    INSERT INTO seeds(
                        id, title, text, keywords, cue, approved, consent_status,
                        consent_model, approved_at, created_at, updated_at, chroma_memory_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        text = excluded.text,
                        keywords = excluded.keywords,
                        cue = excluded.cue,
                        approved = excluded.approved,
                        consent_status = excluded.consent_status,
                        consent_model = excluded.consent_model,
                        approved_at = excluded.approved_at,
                        updated_at = excluded.updated_at,
                        chroma_memory_id = excluded.chroma_memory_id
                    """,
                    (
                        seed_id,
                        seed["title"],
                        seed["text"],
                        _json_dumps(seed["keywords"]),
                        _json_dumps(seed["cue"]),
                        1 if approved else 0,
                        consent.get("status", "pending"),
                        consent.get("model", ""),
                        approved_at,
                        seed["createdAt"],
                        now,
                        chroma_memory_id,
                    ),
                )
                if _consent_changed(prior, approved, str(consent.get("status", "pending")), approved_at):
                    conn.execute(
                        """
                        INSERT INTO consent_logs(
                            id, seed_id, action, consent_status, consent_model,
                            approved_at, boundary, note, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            seed_id,
                            "approved" if approved else "removed" if prior and prior["approved"] else "recorded",
                            consent.get("status", "pending"),
                            consent.get("model", ""),
                            approved_at,
                            _json_dumps(boundary),
                            f"Seed '{seed['title']}' consent status is {consent.get('status', 'pending')}.",
                            now,
                        ),
                    )

            normalized_sessions = [
                _normalize_session(session, valid_session_seed_ids)
                for session in sessions
            ]
            for session in normalized_sessions:
                conn.execute(
                    """
                    INSERT INTO sessions(
                        id, started_at, ended_at, status, approved_seed_ids,
                        cue_events, uncued_seed_ids, settings, safety_boundary,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        ended_at = excluded.ended_at,
                        status = excluded.status,
                        approved_seed_ids = excluded.approved_seed_ids,
                        cue_events = excluded.cue_events,
                        uncued_seed_ids = excluded.uncued_seed_ids,
                        settings = excluded.settings,
                        safety_boundary = excluded.safety_boundary,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session["id"],
                        session["startedAt"],
                        session.get("endedAt"),
                        session["status"],
                        _json_dumps(session["approvedSeedIds"]),
                        _json_dumps(session["cueEvents"]),
                        _json_dumps(session["uncuedSeedIds"]),
                        _json_dumps(session["settings"]),
                        _json_dumps(session["safetyBoundary"]),
                        now,
                        now,
                    ),
                )

            session_lookup = {str(session["id"]): session for session in normalized_sessions}
            for result in recall_results:
                normalized = _normalize_recall_result(result, session_lookup, seed_titles)
                conn.execute(
                    """
                    INSERT INTO recall_results(
                        id, session_id, session_started_at, seed_id, seed_title,
                        condition, answer, score, checked_at, consent_model, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        session_id = excluded.session_id,
                        session_started_at = excluded.session_started_at,
                        seed_id = excluded.seed_id,
                        seed_title = excluded.seed_title,
                        condition = excluded.condition,
                        answer = excluded.answer,
                        score = excluded.score,
                        checked_at = excluded.checked_at,
                        consent_model = excluded.consent_model
                    """,
                    (
                        normalized["id"],
                        normalized["sessionId"],
                        normalized.get("sessionStartedAt"),
                        normalized["seedId"],
                        normalized["seedTitle"],
                        normalized["condition"],
                        normalized["answer"],
                        normalized["score"],
                        normalized["checkedAt"],
                        normalized["consentModel"],
                        now,
                    ),
                )

        return self.get_state()

    def reset(self) -> dict[str, Any]:
        with sqlite3.connect(self.sqlite_path) as conn:
            memory_ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT chroma_memory_id FROM seeds WHERE chroma_memory_id != ''"
                ).fetchall()
            ]
            for table in ["recall_results", "sessions", "consent_logs", "seeds"]:
                conn.execute(f"DELETE FROM {table}")
        for memory_id in memory_ids:
            self._delete_semantic_seed(memory_id)
        return self.get_state()

    def _chroma_collection(self) -> Any | None:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        except Exception:
            return None

        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(
            "neuroseed_memory",
            embedding_function=DefaultEmbeddingFunction(),
        )
        return self._collection

    def _upsert_semantic_seed(self, memory_id: str, seed: dict[str, Any]) -> None:
        collection = self._chroma_collection()
        if collection is None:
            return
        cue = _as_dict(seed.get("cue"))
        keywords = ", ".join(str(word) for word in seed.get("keywords", []))
        document = (
            f"NeuroSeed approved memory seed: {seed['title']}\n"
            f"Content: {seed['text']}\n"
            f"Keywords: {keywords}\n"
            f"Cue: {cue.get('label', '')}"
        )
        collection.upsert(
            ids=[memory_id],
            documents=[document],
            metadatas=[{
                "project": "07-NeuroSeed",
                "category": "approved_seed",
                "seed_id": str(seed["id"]),
                "title": str(seed["title"]),
                "cue": str(cue.get("label", "")),
                "consent_model": str(_as_dict(seed["consent"]).get("model", "")),
                "approved_at": str(_as_dict(seed["consent"]).get("approvedAt", "")),
            }],
        )

    def _delete_semantic_seed(self, memory_id: str) -> None:
        collection = self._chroma_collection()
        if collection is None:
            return
        try:
            collection.delete(ids=[memory_id])
        except Exception:
            pass


def _normalize_seed(value: object) -> dict[str, Any]:
    raw = _as_dict(value)
    seed_id = _clean_str(raw.get("id"), str(uuid4()))
    consent = _as_dict(raw.get("consent"))
    cue = _as_dict(raw.get("cue"))
    return {
        "id": seed_id,
        "title": _clean_str(raw.get("title"), "Untitled seed")[:160],
        "text": _clean_str(raw.get("text"))[:4000],
        "keywords": _clip_list(raw.get("keywords"), limit=12),
        "cue": {
            "type": _clean_str(cue.get("type"), "audio")[:40],
            "label": _clean_str(cue.get("label"), "CUE")[:80],
            "tones": [
                int(item)
                for item in _as_list(cue.get("tones"))
                if isinstance(item, (int, float)) and 20 <= int(item) <= 20000
            ][:8],
            "pattern": [
                int(item)
                for item in _as_list(cue.get("pattern"))
                if isinstance(item, (int, float)) and 0 <= int(item) <= 5000
            ][:12],
        },
        "approved": bool(raw.get("approved")),
        "consent": {
            "status": _clean_str(consent.get("status"), "pending")[:80],
            "model": _clean_str(consent.get("model"), CONSENT_MODEL_VERSION)[:120],
            "approvedAt": _clean_str(consent.get("approvedAt")) or None,
        },
        "createdAt": _clean_str(raw.get("createdAt"), _now()),
    }


def _normalize_session(value: object, valid_seed_ids: set[str]) -> dict[str, Any]:
    raw = _as_dict(value)
    approved_ids = _clip_list(raw.get("approvedSeedIds"), limit=500)
    if any(seed_id not in valid_seed_ids for seed_id in approved_ids):
        raise ValueError("Session contains seed ids without awake approval.")

    settings = _as_dict(raw.get("settings"))
    allowed_stages = set(_clip_list(settings.get("allowedStages"), limit=8)) or {"N2", "N3"}
    cue_events: list[dict[str, Any]] = []
    for event in _as_list(raw.get("cueEvents")):
        cue = _as_dict(event)
        seed_id = _clean_str(cue.get("seedId"))
        stage = _clean_str(cue.get("stage"))
        if seed_id not in approved_ids:
            raise ValueError("Cue event references a seed outside session approval.")
        if stage and stage not in allowed_stages:
            raise ValueError("Cue event is outside the approved sleep-stage window.")
        cue_events.append({
            "seedId": seed_id,
            "seedTitle": _clean_str(cue.get("seedTitle"))[:160],
            "cueLabel": _clean_str(cue.get("cueLabel"))[:80],
            "stage": stage,
            "cuedAt": _clean_str(cue.get("cuedAt"), _now()),
        })

    cued_ids = {str(event["seedId"]) for event in cue_events}
    status = _clean_str(raw.get("status"), "completed")[:40]
    if status not in {"running", "completed", "stopped"}:
        status = "completed"
    return {
        "id": _clean_str(raw.get("id"), str(uuid4())),
        "startedAt": _clean_str(raw.get("startedAt"), _now()),
        "endedAt": _clean_str(raw.get("endedAt")) or None,
        "status": status,
        "approvedSeedIds": approved_ids,
        "cueEvents": cue_events,
        "uncuedSeedIds": [seed_id for seed_id in approved_ids if seed_id not in cued_ids],
        "settings": {
            "maxCues": int(settings.get("maxCues", 0) or 0),
            "volume": int(settings.get("volume", 0) or 0),
            "haptic": int(settings.get("haptic", 0) or 0),
            "allowedStages": sorted(allowed_stages),
        },
        "safetyBoundary": _as_dict(raw.get("safetyBoundary")),
    }


def _normalize_recall_result(
    value: object,
    sessions: dict[str, dict[str, Any]],
    seed_titles: dict[str, str],
) -> dict[str, Any]:
    raw = _as_dict(value)
    session_id = _clean_str(raw.get("sessionId"), "manual")
    seed_id = _clean_str(raw.get("seedId"))
    session = sessions.get(session_id)
    condition = _clean_str(raw.get("condition"), "uncued")
    if session:
        cue_ids = {str(event.get("seedId")) for event in _as_list(session.get("cueEvents"))}
        approved_ids = set(_clip_list(session.get("approvedSeedIds"), limit=500))
        if seed_id not in approved_ids:
            raise ValueError("Recall result references a seed outside the session.")
        condition = "cued" if seed_id in cue_ids else "uncued"
    if condition not in {"cued", "uncued"}:
        condition = "uncued"
    score = raw.get("score", 0)
    if not isinstance(score, (int, float)):
        score = 0
    return {
        "id": _clean_str(raw.get("id"), str(uuid4())),
        "sessionId": session_id,
        "sessionStartedAt": _clean_str(raw.get("sessionStartedAt"))
        or (session.get("startedAt") if session else None),
        "seedId": seed_id,
        "seedTitle": _clean_str(raw.get("seedTitle"), seed_titles.get(seed_id, seed_id))[:160],
        "condition": condition,
        "answer": _clean_str(raw.get("answer"))[:2000],
        "score": max(0.0, min(1.0, float(score))),
        "checkedAt": _clean_str(raw.get("checkedAt"), _now()),
        "consentModel": _clean_str(raw.get("consentModel"), CONSENT_MODEL_VERSION)[:120],
    }


def _seed_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "title": str(row[1]),
        "text": str(row[2]),
        "keywords": _json_loads(row[3], []),
        "cue": _json_loads(row[4], {}),
        "approved": bool(row[5]),
        "consent": {
            "status": str(row[6]),
            "model": str(row[7]),
            "approvedAt": row[8],
        },
        "createdAt": str(row[9]),
    }


def _consent_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "seedId": str(row[1]),
        "action": str(row[2]),
        "consentStatus": str(row[3]),
        "consentModel": str(row[4]),
        "approvedAt": row[5],
        "boundary": _json_loads(row[6], {}),
        "note": str(row[7]),
        "createdAt": str(row[8]),
    }


def _session_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "startedAt": str(row[1]),
        "endedAt": row[2],
        "status": str(row[3]),
        "approvedSeedIds": _json_loads(row[4], []),
        "cueEvents": _json_loads(row[5], []),
        "uncuedSeedIds": _json_loads(row[6], []),
        "settings": _json_loads(row[7], {}),
        "safetyBoundary": _json_loads(row[8], {}),
    }


def _recall_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "sessionId": str(row[1]),
        "sessionStartedAt": row[2],
        "seedId": str(row[3]),
        "seedTitle": str(row[4]),
        "condition": str(row[5]),
        "answer": str(row[6]),
        "score": float(row[7]),
        "checkedAt": str(row[8]),
        "consentModel": str(row[9]),
    }


def _consent_changed(
    prior: dict[str, Any] | None,
    approved: bool,
    consent_status: str,
    approved_at: object,
) -> bool:
    if prior is None:
        return consent_status != "pending" or approved
    return (
        bool(prior["approved"]) != approved
        or str(prior["consent_status"]) != consent_status
        or prior["approved_at"] != approved_at
    )


def _activity_logs(
    consent_logs: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    logs: list[dict[str, str]] = []
    for item in consent_logs[:20]:
        logs.append({
            "time": str(item.get("createdAt", "")),
            "message": f"Consent: {item.get('note', '')}",
        })
    for session in sessions[:20]:
        for event in _as_list(session.get("cueEvents"))[:20]:
            logs.append({
                "time": str(event.get("cuedAt", "")),
                "message": f"{event.get('stage', 'Cue')}: Reinforced {event.get('seedTitle', 'seed')}.",
            })
    return sorted(logs, key=lambda item: item["time"], reverse=True)[:28]


def _summary(
    seeds: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    recall_results: list[dict[str, Any]],
) -> dict[str, Any]:
    cued_scores = [float(item["score"]) for item in recall_results if item.get("condition") == "cued"]
    uncued_scores = [float(item["score"]) for item in recall_results if item.get("condition") == "uncued"]
    return {
        "seedCount": len(seeds),
        "approvedCount": sum(1 for seed in seeds if seed.get("approved")),
        "sessionCount": len(sessions),
        "recallCount": len(recall_results),
        "cuedRecallAverage": _average(cued_scores),
        "uncuedRecallAverage": _average(uncued_scores),
    }


def _delete_rows_not_in(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    keep_ids: set[str],
) -> None:
    if keep_ids:
        placeholders = ",".join("?" for _ in keep_ids)
        conn.execute(
            f"DELETE FROM {table} WHERE {column} NOT IN ({placeholders})",
            tuple(keep_ids),
        )
    else:
        conn.execute(f"DELETE FROM {table}")


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _json_loads(value: object, fallback: object) -> object:
    if not isinstance(value, str) or not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _clean_str(value: object, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _clip_list(values: object, limit: int = 32) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_clean_str(value) for value in values if _clean_str(value)][:limit]


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
