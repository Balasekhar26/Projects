"""Attention Layer (Layer 2).

Saliency classification, intent analysis, focus entity extraction, stakes analysis, and routing paths.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class Attention:
    @classmethod
    def _strip_operator_prefix(cls, message: str) -> str:
        lines = message.splitlines()
        if lines and lines[0].startswith("[operator mode:"):
            return "\n".join(lines[1:]).strip()
        return message

    @classmethod
    def process(cls, observation_frame: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates intent, focus keywords, stakes, required confidence, and selects path."""
        raw_message = observation_frame["raw_message"]
        session_id = observation_frame["session_id"]
        current_msg_id = observation_frame.get("current_message_id") or ""

        clean_message = cls._strip_operator_prefix(raw_message)
        lower_msg = clean_message.lower()

        # Stakes & Reversibility analysis (Triage)
        destructive_keywords = {
            "delete", "rm", "drop", "truncate", "kill", "format", "wipe", "erase",
            "overwrite", "commit", "push", "deploy", "send email"
        }
        is_irreversible = any(re.search(rf"\b{re.escape(word)}\b", lower_msg) for word in destructive_keywords)
        reversibility = "irreversible" if is_irreversible else "reversible"
        stakes_level = "high" if is_irreversible else "low"

        # Check early exits ONLY if the task is not high stakes / irreversible
        if not is_irreversible:
            # 1. Early exit check: Fast Path
            try:
                from backend.main import handle_fast_path
                fast_payload = handle_fast_path(raw_message)
                if fast_payload:
                    return {
                        "focus_keywords": [],
                        "intent_type": "fast_path",
                        "complexity_level": 1,
                        "requires_tools": False,
                        "clean_message": clean_message,
                        "early_exit": {"type": "fast_path", "payload": fast_payload},
                        "stakes_level": "low",
                        "reversibility": "reversible",
                        "required_confidence": 0.50,
                        "path_selected": "FAST",
                    }
            except ImportError:
                pass

            # 2. Early exit check: RBIL (Level 0)
            from backend.core.rbil import RBIL
            rbil_res = RBIL.process(clean_message, session_id=session_id)
            if rbil_res:
                return {
                    "focus_keywords": [],
                    "intent_type": "rbil",
                    "complexity_level": 1,
                    "requires_tools": False,
                    "clean_message": clean_message,
                    "early_exit": {"type": "rbil", "payload": rbil_res},
                    "stakes_level": "low",
                    "reversibility": "reversible",
                    "required_confidence": 0.50,
                    "path_selected": "FAST",
                }

            # 3. Early exit check: Semantic Response Cache (if safe)
            from backend.core.safety import classify_risk
            from backend.core.adaptive_runtime import SemanticResponseCache

            risk_res = classify_risk(clean_message)
            is_safe = not risk_res.approval_required and not risk_res.blocked

            cached_res, cached_agent = (
                SemanticResponseCache.get(clean_message)
                if is_safe
                else (None, None)
            )
            if cached_res:
                return {
                    "focus_keywords": [],
                    "intent_type": "semantic_cache",
                    "complexity_level": 1,
                    "requires_tools": False,
                    "clean_message": clean_message,
                    "early_exit": {
                        "type": "semantic_cache",
                        "payload": {
                            "response": cached_res,
                            "agent": cached_agent or "semantic_cache",
                        },
                    },
                    "stakes_level": "low",
                    "reversibility": "reversible",
                    "required_confidence": 0.50,
                    "path_selected": "FAST",
                }

            # 4. Early exit check: Direct Model Escalation (Level 1/2)
            escalation_level = RBIL.classify_escalation_level(clean_message)
            if escalation_level in (1, 2):
                role = "fast" if escalation_level == 1 else "general"
                try:
                    from backend.core.model_router import ask_model
                    from backend.main import _build_direct_model_prompt
                    prompt_with_context = _build_direct_model_prompt(
                        clean_message, session_id, current_msg_id
                    )
                    result_text = ask_model(prompt_with_context, role=role)
                    return {
                        "focus_keywords": [],
                        "intent_type": f"direct_model_level_{escalation_level}",
                        "complexity_level": 1,
                        "requires_tools": False,
                        "clean_message": clean_message,
                        "early_exit": {
                            "type": "direct_model",
                            "payload": {
                                "response": result_text,
                                "agent": f"direct_model_level_{escalation_level}",
                                "logs": [f"rbil: escalated to Level {escalation_level} direct model"],
                            },
                        },
                        "stakes_level": "low",
                        "reversibility": "reversible",
                        "required_confidence": 0.50,
                        "path_selected": "FAST",
                    }
                except Exception:
                    pass

        # 5. Analyze complexity
        conjunctions = ["then", "and", "after", "first", "next", "finally"]
        has_conjunction = any(
            re.search(rf"\b{conj}\b", lower_msg) for conj in conjunctions
        )
        complexity_level = 2 if has_conjunction else 1

        # 6. Focus keywords extraction
        words = re.findall(r"\b[a-zA-Z0-9_-]{3,20}\b", lower_msg)
        stop_words = {
            "what", "how", "why", "where", "when", "who", "which", "whose", "whom",
            "this", "that", "these", "those", "have", "with", "from", "your", "mine",
            "please", "tell", "show", "open", "find", "search", "write", "make", "create"
        }
        focus_keywords = [w for w in words if w not in stop_words]

        # Ingest active document programming language as focus keyword if available
        active_doc = observation_frame.get("active_document") or {}
        active_lang = active_doc.get("language") if isinstance(active_doc, dict) else None
        if active_lang and active_lang.lower() not in focus_keywords:
            focus_keywords.append(active_lang.lower())

        # 7. Determine tool requirements
        tool_keywords = [
            "chrome", "browser", "speedtest", "internet", "google", "website", "file",
            "delete", "rm", "create", "write", "code", "run", "execute", "terminal", "shell",
            "install", "pip", "npm"
        ]
        requires_tools = complexity_level > 1 or any(
            kw in lower_msg for kw in tool_keywords
        )

        intent_type = "tool_execution" if requires_tools else "conversational"
        path_selected = "DEEP" if (requires_tools or complexity_level > 1 or is_irreversible) else "MID"
        required_confidence = 0.85 if path_selected == "DEEP" else 0.70

        return {
            "focus_keywords": focus_keywords,
            "intent_type": intent_type,
            "complexity_level": complexity_level,
            "requires_tools": requires_tools,
            "clean_message": clean_message,
            "early_exit": None,
            "stakes_level": stakes_level,
            "reversibility": reversibility,
            "required_confidence": required_confidence,
            "path_selected": path_selected,
        }
