"""
Step 9.0 — Research Loop Scheduler.
Orchestrates the daily pipeline of reading, summarizing, idea extraction, and proposal generation.
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any

from backend.core.research_reader import ResearchReader
from backend.core.research_summarizer import ResearchSummarizer
from backend.core.idea_extractor import IdeaExtractor
from backend.core.proposal_engine import ProposalEngine
from backend.core.config import runtime_data_root
from backend.core.logger import log_event
from backend.core.source_trust_engine import SourceTrustEngine, TrustLevel
from backend.core.research_memory import ResearchMemory


def _history_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "research_loop_history.json"


class ResearchScheduler:
    _lock = threading.RLock()
    _thread: threading.Thread | None = None
    _stop_event = threading.Event()
    _last_run_time: float | None = None

    @classmethod
    def _load_history(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _history_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def _save_history(cls, history: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    @classmethod
    def start(cls) -> None:
        """Starts the daily background research loop thread."""
        with cls._lock:
            cls.stop()
            cls._stop_event.clear()
            cls._thread = threading.Thread(target=cls._scheduler_loop, daemon=True)
            cls._thread.start()
            log_event("research_scheduler: daemon thread started successfully.")

    @classmethod
    def stop(cls) -> None:
        """Stops the daily background research loop thread."""
        with cls._lock:
            cls._stop_event.set()
            if cls._thread is not None:
                cls._thread.join(timeout=2.0)
                cls._thread = None
                log_event("research_scheduler: daemon thread stopped.")

    @classmethod
    def _scheduler_loop(cls) -> None:
        """Runs the research loop every 24 hours."""
        # Run immediately on start, then sleep
        try:
            cls.trigger_run()
        except Exception as exc:
            log_event(f"research_scheduler: initial startup run failed: {exc}")

        while not cls._stop_event.is_set():
            # Sleep in 1s increments to respond quickly to shutdowns
            for _ in range(86400):
                if cls._stop_event.is_set():
                    break
                time.sleep(1.0)
            if cls._stop_event.is_set():
                break

            try:
                cls.trigger_run()
            except Exception as exc:
                log_event(f"research_scheduler: periodic run failed: {exc}")

    @classmethod
    def trigger_run(cls, custom_sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Manually trigger a synchronous execution of the pipeline."""
        log_event("research_scheduler: pipeline run triggered.")
        
        # 1. Read Sources
        new_docs = ResearchReader.read_sources(custom_sources=custom_sources)
        
        # Load all read documents to compute consensus across sources
        from backend.core.research_reader import ResearchReader as ReaderClass
        existing_docs = ReaderClass._load_documents()
        all_docs = existing_docs + new_docs
        
        summaries_created = 0
        ideas_extracted = 0
        proposals_created = 0
        proposals_rejected = 0
        
        # 2. Process each new doc
        for doc in new_docs:
            try:
                # Skip already summarized docs
                if ResearchMemory.is_duplicate_summary(doc["id"]):
                    continue

                # Skip documents from REJECTED sources
                doc_source = doc.get("source", "Unknown")
                rep_data = SourceTrustEngine.get_source_reputation(doc_source)
                if rep_data.get("trust_level") == TrustLevel.REJECTED.value:
                    continue

                # Dynamic consensus calculation across all available sources for this title/claim
                doc_title = doc.get("title", "").strip().lower()
                matching_sources = []
                for d in all_docs:
                    d_title = d.get("title", "").strip().lower()
                    if d_title == doc_title or d_title in doc_title or doc_title in d_title:
                        matching_sources.append(d.get("source", "Unknown"))
                matching_sources = list(set(matching_sources))
                
                consensus = SourceTrustEngine.calculate_consensus(matching_sources)
                if consensus < 0.50:
                    log_event(f"research_scheduler: claim consensus score {consensus:.2f} is below 0.50 for doc '{doc.get('title')}'. Blocking proposal.")
                    proposals_rejected += 1
                    continue

                summary = ResearchSummarizer.summarize_document(doc)
                summaries_created += 1
                ResearchMemory.record_summarized(doc["id"])
                
                # 3. Extract Ideas
                ideas = IdeaExtractor.extract_ideas(summary)
                
                # 4. Generate Proposals
                for idea in ideas:
                    ideas_extracted += 1
                    
                    evidence_str = ", ".join(idea.get("evidence", []))
                    if not evidence_str:
                        evidence_str = "Research evidence from document."
                        
                    prop = ProposalEngine.create_proposal(
                        title=idea.get("title", "Optimization Proposal"),
                        problem=idea.get("problem", "Identified system bottleneck"),
                        evidence=evidence_str,
                        proposal=idea.get("proposed_solution", "Apply system adjustments"),
                        expected_gain=idea.get("expected_benefit", 1.5),
                        complexity=1,
                        confidence=85,
                        affected_modules=[],
                        source_name=doc_source
                    )
                    
                    if prop.get("status") == "rejected":
                        proposals_rejected += 1
                    else:
                        proposals_created += 1
                        
            except Exception as exc:
                log_event(f"research_scheduler: error processing document '{doc.get('title')}': {exc}")

        cls._last_run_time = time.time()
        
        run_record = {
            "timestamp": cls._last_run_time,
            "documents_read": len(new_docs),
            "summaries_generated": summaries_created,
            "ideas_extracted": ideas_extracted,
            "proposals_created": proposals_created,
            "proposals_rejected": proposals_rejected,
        }
        
        with cls._lock:
            history = cls._load_history()
            history.append(run_record)
            cls._save_history(history)
            
        log_event(f"research_scheduler: pipeline run complete: {run_record}")
        return run_record

    @classmethod
    def get_last_run_time(cls) -> float | None:
        if cls._last_run_time is not None:
            return cls._last_run_time
        # Fallback to loading history
        history = cls._load_history()
        if history:
            return history[-1].get("timestamp")
        return None
