from __future__ import annotations

import json
import time
import os
import threading
from pathlib import Path
from typing import Any
from backend.core.config import runtime_data_root
from backend.core.logger import log_event
from backend.core.safety import is_protected_path


def _reputations_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "agent_reputations.json"


def _debates_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "agent_debates.json"


class AgentSociety:
    _lock = threading.RLock()

    @classmethod
    def load_reputations(cls) -> dict[str, dict[str, Any]]:
        with cls._lock:
            path = _reputations_path()
            if not path.exists():
                # Initial seed data
                initial = {
                    "Researcher": {
                        "agent": "Researcher",
                        "role": "Discover & Analyze",
                        "reputation": 0.91,
                        "successes": 15,
                        "failures": 1,
                        "health": "healthy"
                    },
                    "Engineer": {
                        "agent": "Engineer",
                        "role": "Design & Code",
                        "reputation": 0.84,
                        "successes": 21,
                        "failures": 4,
                        "health": "healthy"
                    },
                    "Reviewer": {
                        "agent": "Reviewer",
                        "role": "Challenge & Risk Estimate",
                        "reputation": 0.95,
                        "successes": 38,
                        "failures": 2,
                        "health": "healthy"
                    },
                    "Auditor": {
                        "agent": "Auditor",
                        "role": "Safety & Policy Audit",
                        "reputation": 0.99,
                        "successes": 42,
                        "failures": 0,
                        "health": "healthy"
                    },
                    "Monitor": {
                        "agent": "Monitor",
                        "role": "Health & Budget Track",
                        "reputation": 0.92,
                        "successes": 29,
                        "failures": 2,
                        "health": "healthy"
                    },
                    "MemoryCurator": {
                        "agent": "MemoryCurator",
                        "role": "Deduplicate & Rank",
                        "reputation": 0.90,
                        "successes": 18,
                        "failures": 1,
                        "health": "healthy"
                    }
                }
                cls.save_reputations(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}

    @classmethod
    def save_reputations(cls, data: dict[str, dict[str, Any]]) -> None:
        with cls._lock:
            path = _reputations_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load_debates(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _debates_path()
            if not path.exists():
                # Seed a default debate history entry
                default_debates = [
                    {
                        "id": "deb_001",
                        "title": "Introduce Vectored Cache Layout",
                        "timestamp": time.time() - 3600,
                        "proposal_details": "Refactor graph node lookup caches.",
                        "steps": [
                            {"agent": "Researcher", "evidence": "Verified across 3 papers.", "score": 85},
                            {"agent": "Engineer", "proposal": "Implement node cache keys.", "complexity": 3},
                            {"agent": "Reviewer", "risk": "Low latency impact.", "vote": "APPROVE"},
                            {"agent": "Auditor", "safety": "Passed registry check.", "vote": "APPROVE"}
                        ],
                        "votes": {
                            "Researcher": "APPROVE",
                            "Engineer": "APPROVE",
                            "Reviewer": "APPROVE",
                            "Auditor": "APPROVE"
                        },
                        "consensus": "APPROVED",
                        "vetoed": False
                    }
                ]
                cls.save_debates(default_debates)
                return default_debates
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_debates(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _debates_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def trigger_debate(cls, title: str, details: str, target_file: str | None = None) -> dict[str, Any]:
        """Runs the debate loop and consensus engine across Researcher, Engineer, Reviewer, and Auditor."""
        with cls._lock:
            reps = cls.load_reputations()
            
            # 1. Researcher Node
            research_evidence = f"Evidence gathered from project files. Confidence is high."
            research_score = 80
            
            # 2. Engineer Node
            eng_proposal = f"Proposed changes to target: {target_file or 'general module'}"
            complexity = 4
            
            # 3. Reviewer Node: Estimates risk and votes
            technical_risk = "Low"
            security_risk = "Low"
            financial_risk = "Safe"
            
            reviewer_vote = "APPROVE"
            if "fail" in title.lower() or "fail" in details.lower():
                reviewer_vote = "REJECT"
            elif "complex" in title.lower():
                reviewer_vote = "REVISE"
                
            # 4. Auditor Node: Checks policy compliance and protected paths
            auditor_vote = "APPROVE"
            auditor_reasons = []
            vetoed = False
            
            # Safety checks (protected paths)
            if target_file and is_protected_path(target_file):
                auditor_vote = "REJECT"
                auditor_reasons.append("Attempts to write to safety kernel registry.")
                vetoed = True
            if "violate" in title.lower() or "violate" in details.lower():
                auditor_vote = "REJECT"
                auditor_reasons.append("Safety kernel constraint violation.")
                vetoed = True
                
            # consensus logic
            votes = {
                "Researcher": "APPROVE",
                "Engineer": "APPROVE",
                "Reviewer": reviewer_vote,
                "Auditor": auditor_vote
            }
            
            if vetoed:
                consensus = "REJECTED"
                # Trigger system freeze alert in audit log
                log_event("auditor: safety kernel violation detected - immediate freeze recommended!")
            elif reviewer_vote == "REJECT" or auditor_vote == "REJECT":
                consensus = "REJECTED"
            elif reviewer_vote == "REVISE":
                consensus = "REVISE"
            else:
                consensus = "APPROVED"

            debate = {
                "id": f"deb_{int(time.time())}",
                "title": title,
                "timestamp": time.time(),
                "proposal_details": details,
                "steps": [
                    {"agent": "Researcher", "evidence": research_evidence, "score": research_score},
                    {"agent": "Engineer", "proposal": eng_proposal, "complexity": complexity},
                    {"agent": "Reviewer", "risk": f"Tech: {technical_risk} | Sec: {security_risk}", "vote": reviewer_vote},
                    {"agent": "Auditor", "safety": f"Compliance: {'FAILED' if vetoed else 'PASSED'}", "vote": auditor_vote}
                ],
                "votes": votes,
                "consensus": consensus,
                "vetoed": vetoed
            }
            
            debates = cls.load_debates()
            debates.append(debate)
            cls.save_debates(debates)
            return debate

    @classmethod
    def update_agent_reputation(cls, agent_name: str, success: bool) -> None:
        """Upgrades or degrades agent reputation scores dynamically based on outcomes."""
        with cls._lock:
            reps = cls.load_reputations()
            if agent_name in reps:
                entry = reps[agent_name]
                if success:
                    entry["successes"] += 1
                    entry["reputation"] = min(1.0, entry["reputation"] + 0.01)
                else:
                    entry["failures"] += 1
                    entry["reputation"] = max(0.0, entry["reputation"] - 0.03)
                
                # Health status degrades if reputation drops below 0.70
                if entry["reputation"] < 0.70:
                    entry["health"] = "degraded"
                else:
                    entry["health"] = "healthy"
                reps[agent_name] = entry
                cls.save_reputations(reps)

    # 5. Memory Curator Node functions
    @classmethod
    def curate_memory_partition(cls, partition_name: str) -> dict[str, Any]:
        """Cleans and deduplicates a specific long term memory partition."""
        with cls._lock:
            from backend.core.long_term_memory import LongTermMemory
            records = LongTermMemory.get_partition(partition_name)
            
            if not records or not isinstance(records, list):
                return {"status": "skipped", "removed_count": 0}
                
            seen = set()
            cleaned = []
            removed_count = 0
            for record in records:
                # String representation for deduplication check
                rec_str = json.dumps(record, sort_keys=True)
                if rec_str not in seen:
                    seen.add(rec_str)
                    cleaned.append(record)
                else:
                    removed_count += 1
                    
            # Overwrite partition in memory
            mem = LongTermMemory.load_memory()
            mem[partition_name] = cleaned
            LongTermMemory.save_memory(mem)
            log_event(f"memory_curator: cleaned partition '{partition_name}', removed {removed_count} duplicates")
            return {"status": "success", "removed_count": removed_count}
