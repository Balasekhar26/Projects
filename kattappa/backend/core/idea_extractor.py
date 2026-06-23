"""
Step 9.0 — Idea Extractor module.
Converts research summaries and findings into concrete ideas.
"""
from __future__ import annotations

import json
import re
import time
import uuid
import threading
from pathlib import Path
from typing import Any

from backend.core.model_router import ask_model
from backend.core.logger import log_event
from backend.core.config import runtime_data_root


def _ideas_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "research_ideas.json"


class IdeaExtractor:
    _lock = threading.RLock()

    @classmethod
    def _load_ideas(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _ideas_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def _save_ideas(cls, ideas: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _ideas_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ideas, indent=2), encoding="utf-8")

    @classmethod
    def extract_ideas(cls, summary: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract ideas from a summary using ask_model. Fallback to heuristics on failures."""
        sum_id = summary.get("id")
        title = summary.get("title", "")
        summary_text = summary.get("summary", "")
        findings = summary.get("key_findings", [])
        
        prompt = (
            f"You are an expert AI Idea Extractor. Extract actionable ideas from this research summary.\n"
            f"Title: {title}\n"
            f"Summary: {summary_text}\n"
            f"Key Findings: {json.dumps(findings)}\n\n"
            f"Respond strictly in JSON format matching this schema:\n"
            f"{{\n"
            f"  \"ideas\": [\n"
            f"    {{\n"
            f"      \"problem\": \"The specific bottleneck/issue to address\",\n"
            f"      \"proposed_solution\": \"The concrete code/algorithm suggestion\",\n"
            f"      \"expected_benefit\": 0.0-10.0 float expected gain in performance,\n"
            f"      \"evidence\": [\"specific finding or claim from text supporting this\"]\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"Do not include any outer commentary or markdown code blocks."
        )

        ideas_list = []
        try:
            response = ask_model(prompt, role="coder")
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                raw_ideas = data.get("ideas", [])
                if isinstance(raw_ideas, list):
                    for item in raw_ideas:
                        prob = str(item.get("problem", "")).strip()
                        sol = str(item.get("proposed_solution", "")).strip()
                        benefit = item.get("expected_benefit", 1.5)
                        evid = item.get("evidence", [])
                        if isinstance(evid, list):
                            evid = [str(e).strip() for e in evid if e]
                        else:
                            evid = [str(evid).strip()] if evid else []
                        
                        if prob and sol:
                            ideas_list.append({
                                "problem": prob,
                                "proposed_solution": sol,
                                "expected_benefit": float(benefit),
                                "evidence": evid
                            })
            else:
                log_event("idea_extractor: no JSON found in LLM response, invoking fallback.")
        except Exception as exc:
            log_event(f"idea_extractor: LLM call failed: {exc}. Invoking fallback.")

        # Fallback implementation if no ideas extracted
        if not ideas_list:
            title_lower = title.lower()
            if "memory" in title_lower:
                ideas_list.append({
                    "problem": "Episodic memory search has high complexity and slows down runtime.",
                    "proposed_solution": "Implement dynamic compression and memory consolidation sweeps.",
                    "expected_benefit": 3.5,
                    "evidence": ["Findings indicate memory compression reduces search latency."]
                })
            elif "skepticism" in title_lower or "filter" in title_lower:
                ideas_list.append({
                    "problem": "Unfiltered LLM proposals cause high sandbox failure rates.",
                    "proposed_solution": "Add Occam gate skepticism filter comparing expected ROI.",
                    "expected_benefit": 2.0,
                    "evidence": ["Prior sandbox results confirm ROI-based filtering limits waste."]
                })
            else:
                ideas_list.append({
                    "problem": f"System requires dynamic optimization for better efficiency regarding '{title}'.",
                    "proposed_solution": f"Implement structured system optimization based on '{title}'.",
                    "expected_benefit": 1.5,
                    "evidence": ["Extracted from research findings regarding general system topology."]
                })

        # Add metadata and persist
        final_ideas = []
        for idea in ideas_list:
            idea_entry = {
                "id": f"idea_{uuid.uuid4().hex[:12]}",
                "summary_id": sum_id,
                "title": title,
                "problem": idea["problem"],
                "proposed_solution": idea["proposed_solution"],
                "expected_benefit": idea["expected_benefit"],
                "evidence": idea["evidence"],
                "timestamp": time.time(),
            }
            final_ideas.append(idea_entry)

        with cls._lock:
            stored = cls._load_ideas()
            stored.extend(final_ideas)
            cls._save_ideas(stored)

        return final_ideas
