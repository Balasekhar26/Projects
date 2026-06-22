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


TRUST_LEVELS = {
    "reproduced": "High",
    "peer_reviewed": "Medium",
    "preprint": "Low",
    "blog": "Very Low",
}


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
        source_type: str = "peer_reviewed",
    ) -> dict[str, Any]:
        """Analyzes a research paper, blog post, or documentation using ask_model as a Research Advisor.
        
        Persists the structured analysis report to research_results.json and returns it.
        """
        source_type = source_type.strip().lower()
        
        # Source checks and trust level mapping
        if "social" in source_type:
            raise ValueError("Social posts are ignored for research analysis.")
            
        normalized_source = "peer_reviewed"
        if "reproduced" in source_type:
            normalized_source = "reproduced"
        elif "preprint" in source_type:
            normalized_source = "preprint"
        elif "blog" in source_type:
            normalized_source = "blog"
        elif "document" in source_type or "paper" in source_type:
            normalized_source = "peer_reviewed"
            
        trust_level = TRUST_LEVELS.get(normalized_source, "Medium")

        # Check for Protected Core touches locally first (strict safety boundary)
        protected_keywords = {
            "validators", "policy_engine", "consensus_engine", "value_engine",
            "benchmark_arena", "reliability_monitor", "proposal_governance",
            "approval_gates", "deployment_controls", "deployment_controller",
            "main.py", "reliability", "execution_policy"
        }
        
        touches_protected_core_local = False
        content_lower = content.lower()
        for keyword in protected_keywords:
            if keyword in content_lower:
                touches_protected_core_local = True
                break

        prompt = (
            f"You are a Research Advisor analyzing {normalized_source} material titled '{title}'.\n"
            f"Analyze the material in the context of our existing Kattappa self-improvement pipeline.\n"
            f"--- CONTENT ---\n{content[:6000]}\n---------------\n\n"
            f"Requirements:\n"
            f"1. Summarize the text and extract specific ideas/claims.\n"
            f"2. Compare this material against the current system (Kattappa):\n"
            f"   - What capability exists already in the system?\n"
            f"   - What capability is missing?\n"
            f"   - What risks exist?\n"
            f"   - Does it touch the protected core?\n"
            f"3. Respond strictly with a JSON object matching this schema:\n"
            f"{{\n"
            f"  \"summary\": \"Concise paragraph summary of the text\",\n"
            f"  \"ideas\": [\"list of specific ideas suggested by this text\"],\n"
            f"  \"usefulness_score\": 0-100 integer,\n"
            f"  \"implementation_difficulty\": 0-100 integer,\n"
            f"  \"comparison\": {{\n"
            f"    \"existing_capability\": \"What exists already in the system regarding this\",\n"
            f"    \"missing_capability\": \"What capability is missing in the system\",\n"
            f"    \"evidence_strength\": \"Strength of evidence in this material\",\n"
            f"    \"risks\": \"Potential risks of implementing this\",\n"
            f"    \"touches_protected_core\": true/false\n"
            f"  }},\n"
            f"  \"claims\": [\n"
            f"    {{\n"
            f"      \"claim\": \"Extracted claim\",\n"
            f"      \"source_type\": \"{normalized_source}\",\n"
            f"      \"verification\": \"unverified\"\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"Do not include any outer commentary or formatting outside the JSON."
        )

        summary = ""
        ideas = []
        usefulness_score = 50
        implementation_difficulty = 50
        comparison = {
            "existing_capability": "Unknown",
            "missing_capability": "Unknown",
            "evidence_strength": "Unverified",
            "risks": "Unverified",
            "touches_protected_core": touches_protected_core_local,
        }
        claims = []

        try:
            response = ask_model(prompt, role="coder")
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
                    
                    u_score = data.get("usefulness_score", 50)
                    usefulness_score = max(0, min(100, int(u_score)))
                    
                    d_score = data.get("implementation_difficulty", 50)
                    implementation_difficulty = max(0, min(100, int(d_score)))

                    # Parse comparison
                    raw_comp = data.get("comparison", {})
                    if isinstance(raw_comp, dict):
                        comparison["existing_capability"] = str(raw_comp.get("existing_capability", "Unknown")).strip()
                        comparison["missing_capability"] = str(raw_comp.get("missing_capability", "Unknown")).strip()
                        comparison["evidence_strength"] = str(raw_comp.get("evidence_strength", "Unverified")).strip()
                        comparison["risks"] = str(raw_comp.get("risks", "Unverified")).strip()
                        comp_touches = raw_comp.get("touches_protected_core", touches_protected_core_local)
                        comparison["touches_protected_core"] = bool(comp_touches) or touches_protected_core_local
                    
                    # Parse claims
                    raw_claims = data.get("claims", [])
                    if isinstance(raw_claims, list):
                        for c in raw_claims:
                            if isinstance(c, dict) and "claim" in c:
                                claims.append({
                                    "claim": str(c["claim"]).strip(),
                                    "source_type": normalized_source,
                                    "verification": "unverified"
                                })
                except Exception as exc:
                    log_event(f"research_agent: failed to parse LLM JSON response: {exc}")
            else:
                log_event("research_agent: no JSON object found in response.")
        except Exception as exc:
            log_event(f"research_agent: LLM analysis failed: {exc}")

        # Fallbacks
        if not summary:
            summary = f"Summary of {normalized_source} '{title}': " + (content[:300] + "..." if len(content) > 300 else content)
        if not ideas:
            ideas = [f"Investigate implementation of {title} in the system."]
        if not claims:
            claims = [{
                "claim": f"Implementation of ideas from '{title}'",
                "source_type": normalized_source,
                "verification": "unverified"
            }]

        entry = {
            "id": f"res_{uuid.uuid4().hex[:12]}",
            "title": title,
            "source_type": normalized_source,
            "trust_level": trust_level,
            "summary": summary,
            "ideas": ideas,
            "usefulness_score": usefulness_score,
            "implementation_difficulty": implementation_difficulty,
            "comparison": comparison,
            "claims": claims,
            "timestamp": time.time(),
        }

        with cls._lock:
            results = cls._load_results()
            results.append(entry)
            cls._save_results(results)

        return entry

    @classmethod
    def list_results(cls) -> list[dict[str, Any]]:
        return cls._load_results()
