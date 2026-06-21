from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from backend.core.model_router import ask_model
from backend.core.logger import log_event
from backend.core.reflection_memory import ReflectionMemory


class ReflectionEngine:
    """Reflection Engine (Layer 8 component).
    
    Responsible for analyzing logs and execution traces, performing significance checks,
    and invoking the model to safely generate improvement proposals under governance guidelines.
    """

    @classmethod
    def evaluate_significance(cls, logs_text: str) -> dict[str, Any]:
        """Performs a deterministic significance evaluation on raw log traces.
        
        Analyzes tool exit codes, exception counts, and explicit error matches.
        """
        # Parse common failure indicators:
        # Non-zero exit codes: e.g. "exit_code=1" or similar
        exit_code_failures = len(re.findall(r"exit_code=[1-9]", logs_text))
        
        # Exception patterns
        exceptions = len(re.findall(r"(?i)\b(exception|failed|error|runtimeerror|valueerror|connectionerror)\b", logs_text))
        
        # Thumbs down / user rejection indicators
        thumbs_down = len(re.findall(r"(?i)\b(thumbs down|user rejected|thumbs-down|bad response)\b", logs_text))
        
        total_runs = len(re.findall(r"(?i)\b(run_task|session_start|execute_command)\b", logs_text)) or 1
        
        error_rate = (exit_code_failures + exceptions + thumbs_down) / total_runs
        
        return {
            "exit_code_failures": exit_code_failures,
            "exceptions": exceptions,
            "thumbs_down": thumbs_down,
            "total_runs": total_runs,
            "error_rate": error_rate,
            "actionable": (exit_code_failures > 0 or exceptions > 3 or thumbs_down > 0 or error_rate > 0.05)
        }

    @classmethod
    def analyze_and_propose(cls, logs_text: str, source_window_days: int = 7) -> str | None:
        """Parses interaction logs, runs significance checks, and proposes a reflection candidate.
        
        Returns the created reflection ID, or None if no actionable issue was found.
        """
        sig = cls.evaluate_significance(logs_text)
        
        # If no significant issues exist, do not generate proposals (avoids manufactured problems)
        if not sig["actionable"]:
            log_event("reflection_engine: no significant actionable issue detected in logs.")
            return None
            
        # Invoke model with a clean prompt requesting a structured JSON response
        prompt = (
            f"Analyze the following execution logs and identify the root cause of failures.\n"
            f"--- LOGS ---\n{logs_text[:4000]}\n------------\n\n"
            f"Requirements:\n"
            f"1. Never propose self-modification of source code files.\n"
            f"2. Propose only behavior, retrieval, prompt, or tool parameter improvements.\n"
            f"3. Respond strictly with a JSON object containing these keys:\n"
            f"   - 'category': one of 'RETRIEVAL', 'REASONING', 'TOOLING', 'ALIGNMENT', 'SAFETY', 'PERFORMANCE', 'SUCCESS'\n"
            f"   - 'problem': clear explanation of the failure\n"
            f"   - 'cause': underlying root cause\n"
            f"   - 'improvement': proposed prompt or parameter change proposal (without modifying python files)\n"
            f"   - 'confidence': confidence score between 0.0 and 1.0\n"
            f"4. If nothing is actionable, return the category 'SUCCESS' and empty strings for other fields."
        )
        
        try:
            response = ask_model(prompt, role="coder")
            
            # Simple JSON extraction in case model returned extra markdown backticks
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                log_event("reflection_engine: failed to parse JSON from LLM response. Using deterministic fallback.")
                return cls._create_fallback_reflection(sig, source_window_days)
                
            data = json.loads(json_match.group(0))
            category = data.get("category", "PERFORMANCE").strip().upper()
            problem = data.get("problem", "Log errors detected").strip()
            cause = data.get("cause", "Exceptions / non-zero exits in logs").strip()
            improvement = data.get("improvement", "Improve search parameters or retry limits").strip()
            confidence = float(data.get("confidence", 0.7))
            
            if category == "SUCCESS" or not problem or problem.lower() == "none":
                return None
                
            # Submit to Reflection Memory (which handles deduplication)
            ref_id = ReflectionMemory.propose_reflection(
                category=category,
                problem=problem,
                cause=cause,
                improvement=improvement,
                confidence=confidence,
                source_window_days=source_window_days
            )
            return ref_id
            
        except Exception as exc:
            log_event(f"reflection_engine: LLM analysis failed: {exc}. Falling back to deterministic proposal.")
            return cls._create_fallback_reflection(sig, source_window_days)

    @classmethod
    def _create_fallback_reflection(cls, sig_data: dict, source_window_days: int) -> str:
        """Deterministic partial-capture fallback when LLM schema generation fails."""
        problem = f"Observed {sig_data['exceptions']} exceptions and {sig_data['exit_code_failures']} exit failures."
        cause = "System exit code mismatches or unhandled exceptions."
        improvement = "Increase retry delays or verify prerequisite environment settings."
        
        return ReflectionMemory.propose_reflection(
            category="PERFORMANCE",
            problem=problem,
            cause=cause,
            improvement=improvement,
            confidence=0.6,
            source_window_days=source_window_days
        )
