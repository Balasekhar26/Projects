from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.core.model_router import ask_model
from backend.core.config import runtime_data_root
from backend.core.logger import log_event


def _data_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "research_results.json"


class ResearchAgent:
    _lock = threading.RLock()

    @classmethod
    def _load_results(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _data_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def _save_results(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _data_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save_results([])

    @classmethod
    def analyze_material(
        cls,
        title: str,
        content: str,
        source_type: str = "paper",
    ) -> dict[str, Any]:
        """Analyzes a research paper, blog post, or documentation using ask_model.
        
        Persists the result to research_results.json and returns it.
        """
        source_type = source_type.strip().lower()
        if source_type not in ("paper", "blog", "documentation"):
            if "paper" in source_type:
                source_type = "paper"
            elif "blog" in source_type:
                source_type = "blog"
            else:
                source_type = "documentation"

        prompt = (
            f"Analyze the following {source_type} titled '{title}':\n"
            f"--- CONTENT ---\n{content[:6000]}\n---------------\n\n"
            f"Please summarize it, extract potential ideas, and grade its usefulness "
            f"and implementation difficulty.\n"
            f"You MUST respond strictly with a valid JSON object matching this schema:\n"
            f"{{\n"
            f"  \"summary\": \"Concise paragraph summary of the text\",\n"
            f"  \"ideas\": [\"list of specific implementation ideas/actions suggested by this text\"],\n"
            f"  \"usefulness_score\": 0-100 integer,\n"
            f"  \"implementation_difficulty\": 0-100 integer\n"
            f"}}\n"
            f"Do not include any other commentary, markdown formatting (outside of standard code fence blocks), or text outside the JSON."
        )

        summary = ""
        ideas = []
        usefulness_score = 50
        implementation_difficulty = 50

        try:
            response = ask_model(prompt, role="coder")
            # Parse response using regex extraction
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    summary = str(data.get("summary", "")).strip()
                    raw_ideas = data.get("ideas", [])
                    if isinstance(raw_ideas, list):
                        ideas = [str(x).strip() for x in raw_ideas if x]
                    else:
                        ideas = [str(raw_ideas).strip()] if raw_ideas else []
                    
                    # Ensure score boundaries
                    u_score = data.get("usefulness_score", 50)
                    usefulness_score = max(0, min(100, int(u_score)))
                    
                    d_score = data.get("implementation_difficulty", 50)
                    implementation_difficulty = max(0, min(100, int(d_score)))
                except Exception as exc:
                    log_event(f"research_agent: failed to parse JSON data: {exc}")
            else:
                log_event("research_agent: no JSON object found in response.")
        except Exception as exc:
            log_event(f"research_agent: LLM analysis failed: {exc}")

        # Fallback values if LLM output was completely empty or failed to parse summary
        if not summary:
            summary = f"Summary of {source_type} '{title}': " + (content[:300] + "..." if len(content) > 300 else content)
        if not ideas:
            ideas = [f"Investigate implementation of {title} in the system."]

        # Store result
        entry = {
            "id": f"res_{uuid.uuid4().hex[:12]}",
            "title": title,
            "source_type": source_type,
            "summary": summary,
            "ideas": ideas,
            "usefulness_score": usefulness_score,
            "implementation_difficulty": usefulness_score,  # default placeholder matching
        }
        # Overwrite with correct field value
        entry["implementation_difficulty"] = implementation_difficulty

        with cls._lock:
            results = cls._load_results()
            results.append(entry)
            cls._save_results(results)

        return entry

    @classmethod
    def list_results(cls) -> list[dict[str, Any]]:
        return cls._load_results()
