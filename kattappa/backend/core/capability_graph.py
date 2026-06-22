"""Capability Graph (Tier 1).

The nervous system that connects Goals to the Skills, Knowledge and Tools they
require. Given a goal's required capabilities, it computes what Kattappa already
has, what is missing, and which gaps are bottlenecks — so the system knows its
own limits and can plan around them.

Deterministic and persistent. It assesses; it never executes.
"""

from __future__ import annotations

import json
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "capabilities.json"


class CapabilityKind(str, Enum):
    SKILL = "skill"
    KNOWLEDGE = "knowledge"
    TOOL = "tool"

    @classmethod
    def coerce(cls, value: "CapabilityKind | str") -> "CapabilityKind":
        return value if isinstance(value, cls) else cls(str(value).strip().lower())


class CapabilityGraph:
    _lock = threading.RLock()

    # -- persistence -------------------------------------------------------
    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"capabilities": {}}

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

    # -- registry ----------------------------------------------------------
    @classmethod
    def register(
        cls,
        name: str,
        kind: CapabilityKind | str = CapabilityKind.SKILL,
        *,
        available: bool = True,
        depends_on: list[str] | None = None,
        alternatives: list[str] | None = None,
        risk: str = "",
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Capability name cannot be empty")
        cap = {
            "name": name,
            "kind": CapabilityKind.coerce(kind).value,
            "available": bool(available),
            "depends_on": [d.strip() for d in (depends_on or []) if d.strip()],
            "alternatives": [a.strip() for a in (alternatives or []) if a.strip()],
            "risk": risk,
            "updated_at": time.time(),
        }
        with cls._lock:
            data = cls._load()
            data.setdefault("capabilities", {})[cls._key(name)] = cap
            cls._save(data)
        return cap

    @classmethod
    def get(cls, name: str) -> dict[str, Any] | None:
        return cls._load().get("capabilities", {}).get(cls._key(name))

    @classmethod
    def set_available(cls, name: str, available: bool) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            cap = data.get("capabilities", {}).get(cls._key(name))
            if cap is None:
                raise KeyError(f"No capability {name!r}")
            cap["available"] = bool(available)
            cap["updated_at"] = time.time()
            cls._save(data)
            return cap

    @classmethod
    def list_capabilities(cls) -> list[dict[str, Any]]:
        return list(cls._load().get("capabilities", {}).values())

    # -- assessment --------------------------------------------------------
    @classmethod
    def _satisfied(cls, name: str, caps: dict[str, Any]) -> bool:
        cap = caps.get(cls._key(name))
        if cap and cap.get("available"):
            return True
        # An available alternative also satisfies the requirement.
        if cap:
            for alt in cap.get("alternatives", []):
                alt_cap = caps.get(cls._key(alt))
                if alt_cap and alt_cap.get("available"):
                    return True
        return False

    @classmethod
    def _closure(cls, required: list[str], caps: dict[str, Any]) -> list[str]:
        seen: list[str] = []
        stack = list(required)
        seen_keys: set[str] = set()
        while stack:
            name = stack.pop(0)
            key = cls._key(name)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            seen.append(name)
            cap = caps.get(key)
            if cap:
                stack.extend(cap.get("depends_on", []))
        return seen

    @classmethod
    def assess(cls, goal: str, required: list[str]) -> dict[str, Any]:
        caps = cls._load().get("capabilities", {})
        closure = cls._closure(list(required), caps)

        satisfied = [c for c in closure if cls._satisfied(c, caps)]
        missing = [c for c in closure if not cls._satisfied(c, caps)]

        # Bottlenecks: missing capabilities that other required ones depend on.
        depended_on: set[str] = set()
        for c in closure:
            cap = caps.get(cls._key(c))
            if cap:
                depended_on.update(cls._key(d) for d in cap.get("depends_on", []))
        bottlenecks = [m for m in missing if cls._key(m) in depended_on]

        risks = {}
        alternatives = {}
        for m in missing:
            cap = caps.get(cls._key(m))
            if cap and cap.get("risk"):
                risks[m] = cap["risk"]
            if cap and cap.get("alternatives"):
                alternatives[m] = cap["alternatives"]

        total = len(closure)
        return {
            "goal": goal,
            "required": closure,
            "satisfied": satisfied,
            "missing": missing,
            "bottlenecks": bottlenecks,
            "risks": risks,
            "alternatives": alternatives,
            "coverage": round(len(satisfied) / total, 4) if total else 1.0,
            "can_proceed": not missing,
        }

    @classmethod
    def status(cls) -> dict[str, Any]:
        caps = cls.list_capabilities()
        by_kind: dict[str, int] = {k.value: 0 for k in CapabilityKind}
        available = 0
        for c in caps:
            by_kind[c.get("kind", "skill")] = by_kind.get(c.get("kind", "skill"), 0) + 1
            available += int(bool(c.get("available")))
        return {"total": len(caps), "available": available, "by_kind": by_kind}

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"capabilities": {}})
