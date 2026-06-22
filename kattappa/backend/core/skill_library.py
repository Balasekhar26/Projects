"""Skill Library (Tier 1).

Reusable workflows so tasks don't start from scratch: a skill solved once becomes
a template (inputs -> steps -> outputs) future tasks reuse. Skills track their own
success rate and get promoted from draft to trusted as they prove out.

Deterministic and persistent. A skill is a *template*, never auto-executed.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "skills.json"


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2}


class SkillLibrary:
    _lock = threading.RLock()
    PROMOTE_AFTER = 3
    PROMOTE_RATE = 0.8

    # -- persistence -------------------------------------------------------
    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"skills": {}}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _key(name: str) -> str:
        return name.strip().lower()

    @staticmethod
    def _rate(skill: dict[str, Any]) -> float | None:
        total = skill["success_count"] + skill["failure_count"]
        return skill["success_count"] / total if total else None

    # -- crud --------------------------------------------------------------
    @classmethod
    def add_skill(
        cls,
        name: str,
        description: str = "",
        *,
        inputs: list[str] | None = None,
        steps: list[str] | None = None,
        outputs: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Skill name cannot be empty")
        with cls._lock:
            data = cls._load()
            skills = data.setdefault("skills", {})
            if cls._key(name) in skills:
                raise ValueError(f"Skill {name!r} already exists")
            skill = {
                "id": uuid.uuid4().hex[:12],
                "name": name,
                "description": description.strip(),
                "inputs": list(inputs or []),
                "steps": list(steps or []),
                "outputs": list(outputs or []),
                "tags": [t.strip().lower() for t in (tags or []) if t.strip()],
                "success_count": 0,
                "failure_count": 0,
                "trust": "draft",
                "created_at": time.time(),
            }
            skills[cls._key(name)] = skill
            cls._save(data)
            return skill

    @classmethod
    def get(cls, name: str) -> dict[str, Any] | None:
        return cls._load().get("skills", {}).get(cls._key(name))

    @classmethod
    def list_skills(cls) -> list[dict[str, Any]]:
        return list(cls._load().get("skills", {}).values())

    @classmethod
    def remove(cls, name: str) -> bool:
        with cls._lock:
            data = cls._load()
            if cls._key(name) in data.get("skills", {}):
                del data["skills"][cls._key(name)]
                cls._save(data)
                return True
            return False

    # -- search ------------------------------------------------------------
    @classmethod
    def search(cls, query: str) -> list[dict[str, Any]]:
        q = _tokens(query) | {query.strip().lower()}
        scored: list[tuple[int, dict[str, Any]]] = []
        for skill in cls.list_skills():
            haystack = _tokens(skill["name"]) | _tokens(skill["description"]) | set(skill["tags"])
            score = len(q & haystack)
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda s: (-s[0], s[1]["name"]))
        return [s for _, s in scored]

    @classmethod
    def find_for_tags(cls, tags: list[str]) -> list[dict[str, Any]]:
        want = {t.strip().lower() for t in tags}
        return [s for s in cls.list_skills() if want & set(s["tags"])]

    # -- learning ----------------------------------------------------------
    @classmethod
    def record_result(cls, name: str, success: bool) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            skill = data.get("skills", {}).get(cls._key(name))
            if skill is None:
                raise KeyError(f"No skill {name!r}")
            skill["success_count"] += 1 if success else 0
            skill["failure_count"] += 0 if success else 1
            rate = cls._rate(skill)
            total = skill["success_count"] + skill["failure_count"]
            if (skill["trust"] == "draft" and skill["success_count"] >= cls.PROMOTE_AFTER
                    and rate is not None and rate >= cls.PROMOTE_RATE):
                skill["trust"] = "trusted"
            skill["success_rate"] = round(rate, 4) if rate is not None else None
            skill["uses"] = total
            cls._save(data)
            return skill

    @classmethod
    def status(cls) -> dict[str, Any]:
        skills = cls.list_skills()
        trusted = sum(1 for s in skills if s["trust"] == "trusted")
        return {"total": len(skills), "trusted": trusted, "draft": len(skills) - trusted}

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"skills": {}})
