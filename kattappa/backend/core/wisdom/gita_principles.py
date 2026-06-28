"""Bhagavad Gita Principles — Phase K9.

Loads from gita_principles.yaml and compiles into typed GitaPrinciple objects.
Edit the YAML to add, modify, or version-control wisdom sources without
touching Python code.  Additional wisdom traditions can be added as separate
YAML documents in the future.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GitaPrinciple:
    id: str                                # e.g. "BG-02-47"
    chapter: int
    verse_range: str                       # e.g. "47"
    domain: str                            # primary governance domain
    principle: str                         # one-sentence statement
    guidance: str                          # how to apply it in decision-making
    application_domains: tuple[str, ...]   # domains where this principle applies
    exclusion_domains: tuple[str, ...]     # domains where it must NOT be applied


_YAML_PATH = Path(__file__).parent / "gita_principles.yaml"


@functools.lru_cache(maxsize=1)
def _load_yaml() -> dict[str, Any]:
    with open(_YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=1)
def _build_principles() -> tuple[GitaPrinciple, ...]:
    data = _load_yaml()
    exclusions: tuple[str, ...] = tuple(data.get("technical_exclusions", []))
    result: list[GitaPrinciple] = []
    for raw in data.get("principles", []):
        result.append(GitaPrinciple(
            id=raw["id"],
            chapter=int(raw["chapter"]),
            verse_range=str(raw["verse_range"]),
            domain=raw["domain"],
            principle=raw["principle"].strip(),
            guidance=raw["guidance"].strip(),
            application_domains=tuple(raw.get("application_domains", [])),
            exclusion_domains=exclusions,
        ))
    return tuple(result)


@functools.lru_cache(maxsize=1)
def _build_exclusions() -> tuple[str, ...]:
    return tuple(_load_yaml().get("technical_exclusions", []))


# ── Public constants ───────────────────────────────────────────────────────────

@property
def PRINCIPLES() -> tuple[GitaPrinciple, ...]:  # type: ignore[misc]
    return _build_principles()

# Make PRINCIPLES a module-level tuple (eagerly loaded)
PRINCIPLES: tuple[GitaPrinciple, ...] = _build_principles()


# ── Query helpers ──────────────────────────────────────────────────────────────

def get_principles_for_domain(domain: str) -> list[GitaPrinciple]:
    """Return all principles applicable to a given domain."""
    d = domain.lower()
    return [p for p in PRINCIPLES if d in p.application_domains]


def get_principle_by_id(principle_id: str) -> GitaPrinciple | None:
    for p in PRINCIPLES:
        if p.id == principle_id:
            return p
    return None


def is_excluded_domain(domain: str) -> bool:
    """True if this domain is explicitly excluded from Wisdom Engine guidance."""
    return domain.lower() in _build_exclusions()


def reload_principles() -> tuple[GitaPrinciple, ...]:
    """Force a reload from YAML (useful during development or testing)."""
    _build_principles.cache_clear()
    _build_exclusions.cache_clear()
    _load_yaml.cache_clear()
    return _build_principles()
