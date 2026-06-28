"""Attention Layer (Layer 2) — Attention 2.0.

Saliency classification, intent analysis, focus entity extraction, stakes analysis,
and 5-dimensional priority scoring (Importance, Urgency, Novelty, Risk, Opportunity).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.core.logger import log_event


@dataclass
class AttentionScore:
    importance: float   # 0.0 - 1.0: goal alignment, user urgency
    urgency: float      # 0.0 - 1.0: deadline proximity, time pressure
    novelty: float      # 0.0 - 1.0: distance from known semantic concepts
    risk: float         # 0.0 - 1.0: destructive commands, causal downstream impact
    opportunity: float  # 0.0 - 1.0: long-term capability growth, learning value
    composite: float    # 0.0 - 1.0: weighted sum of the above dimensions

    def to_dict(self) -> dict[str, float]:
        return {
            "importance": self.importance,
            "urgency": self.urgency,
            "novelty": self.novelty,
            "risk": self.risk,
            "opportunity": self.opportunity,
            "composite": self.composite,
        }


class Attention:
    @classmethod
    def _strip_operator_prefix(cls, message: str) -> str:
        lines = message.splitlines()
        if lines and lines[0].startswith("[operator mode:"):
            return "\n".join(lines[1:]).strip()
        return message

    @classmethod
    def process(cls, observation_frame: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates intent, focus keywords, stakes, and 5-dimensional attention score."""
        raw_message = observation_frame["raw_message"]
        session_id = observation_frame["session_id"]
        current_msg_id = observation_frame.get("current_message_id") or ""

        clean_message = cls._strip_operator_prefix(raw_message)
        lower_msg = clean_message.lower()

        # ── 1. Focus keywords extraction ──────────────────────────────────────
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

        # ── 2. Destructive & Reversibility analysis (Triage) ──────────────────
        destructive_keywords = {
            "delete", "rm", "drop", "truncate", "kill", "format", "wipe", "erase",
            "overwrite", "commit", "push", "deploy", "send email"
        }
        is_irreversible = any(re.search(rf"\b{re.escape(word)}\b", lower_msg) for word in destructive_keywords)
        reversibility = "irreversible" if is_irreversible else "reversible"
        stakes_level = "high" if is_irreversible else "low"

        # ── 3. 5-Dimensional Attention Scoring ───────────────────────────────
        
        # A. Importance (Goal alignment & explicit urgency words)
        importance = 0.3
        urgency_terms = {"urgent", "critical", "important", "immediately", "asap", "emergency"}
        if any(term in lower_msg for term in urgency_terms):
            importance += 0.4
        
        try:
            from backend.core.goal_manager import GoalManager
            active_goals = GoalManager.list_goals(status="active")
            for goal in active_goals:
                goal_text = f"{goal.get('title', '')} {goal.get('description', '')}".lower()
                if any(kw in goal_text for kw in focus_keywords):
                    importance += 0.3
                    break
        except Exception:
            pass
        importance = min(1.0, importance)

        # B. Urgency (Deadline proximity)
        urgency = 0.2
        deadline_terms = {"deadline", "due", "by today", "by tomorrow", "soon", "timeline", "seconds", "minutes", "hours"}
        if any(term in lower_msg for term in deadline_terms):
            urgency += 0.4
        if "asap" in lower_msg or "immediately" in lower_msg:
            urgency += 0.3
        urgency = min(1.0, urgency)

        # C. Novelty (Distance from known concepts)
        novelty = 0.5  # default
        try:
            from backend.core.semantic_memory import SemanticMemory
            results = SemanticMemory.recall(query=clean_message, limit=1)
            if results:
                # Concept is known; novelty decreases with higher confidence
                novelty = max(0.1, 1.0 - results[0].get("confidence_score", 0.5))
            else:
                # Concept not found in semantic memory -> high novelty
                novelty = 0.85
        except Exception:
            pass

        # D. Risk (Destructive base + Causal downstream impact)
        risk = 0.1
        if is_irreversible:
            risk = 0.7
        try:
            from backend.core.world_model import WorldModel
            for kw in focus_keywords:
                impact = WorldModel.impact_of(kw)
                if impact:
                    dep_count = impact.get("dependency_count", 0)
                    conflict_count = impact.get("conflict_count", 0)
                    if dep_count > 3 or conflict_count > 0:
                        risk = min(1.0, risk + 0.3)
                        break
        except Exception:
            pass
        risk = min(1.0, risk)

        # E. Opportunity (Long-term growth, learning, optimization)
        opportunity = 0.1
        opp_terms = {"learn", "study", "growth", "improvement", "refactor", "optimize", "mathematics", "physics", "science", "wisdom"}
        if any(term in lower_msg for term in opp_terms):
            opportunity += 0.6
        opportunity = min(1.0, opportunity)

        # F. Composite Score based on dynamic Cognitive State weights
        try:
            from backend.core.state_manager import CognitiveStateManager
            weights = CognitiveStateManager.get_attention_weights()
        except Exception:
            weights = {
                "importance": 0.25,
                "urgency": 0.20,
                "novelty": 0.15,
                "risk": 0.25,
                "opportunity": 0.15,
            }

        composite = (
            (importance * weights["importance"]) +
            (urgency * weights["urgency"]) +
            (novelty * weights["novelty"]) +
            (risk * weights["risk"]) +
            (opportunity * weights["opportunity"])
        )

        # Scale up composite score if domain matches any active failure boosts
        try:
            from backend.core.state_manager import CognitiveStateManager
            boosts = CognitiveStateManager.get_domain_boosts()
            boost_factor = 1.0
            for domain, factor in boosts.items():
                if domain in lower_msg or any(domain in kw for kw in focus_keywords):
                    boost_factor = max(boost_factor, factor)
            composite = min(1.0, composite * boost_factor)
        except Exception:
            pass

        score_obj = AttentionScore(
            importance=round(importance, 3),
            urgency=round(urgency, 3),
            novelty=round(novelty, 3),
            risk=round(risk, 3),
            opportunity=round(opportunity, 3),
            composite=round(composite, 3),
        )

        # Check early exits ONLY if the task is not high stakes / irreversible
        if not is_irreversible:
            # A. Early exit check: Fast Path
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
                        "attention_score": score_obj.to_dict(),
                    }
            except ImportError:
                pass

            # B. Early exit check: RBIL (Level 0)
            try:
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
                        "attention_score": score_obj.to_dict(),
                    }
            except ImportError:
                pass

            # C. Early exit check: Semantic Response Cache (if safe)
            try:
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
                        "attention_score": score_obj.to_dict(),
                    }
            except ImportError:
                pass

            # D. Early exit check: Direct Model Escalation (Level 1/2)
            try:
                from backend.core.rbil import RBIL
                escalation_level = RBIL.classify_escalation_level(clean_message)
                if escalation_level in (1, 2):
                    role = "fast" if escalation_level == 1 else "general"
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
                        "attention_score": score_obj.to_dict(),
                    }
            except Exception:
                pass

        # ── 4. Analyze complexity ─────────────────────────────────────────────
        conjunctions = ["then", "and", "after", "first", "next", "finally"]
        has_conjunction = any(
            re.search(rf"\b{conj}\b", lower_msg) for conj in conjunctions
        )
        complexity_level = 2 if has_conjunction else 1

        # ── 5. Path Selection ─────────────────────────────────────────────────
        tool_keywords = [
            "chrome", "browser", "speedtest", "internet", "google", "website", "file",
            "delete", "rm", "create", "write", "code", "run", "execute", "terminal", "shell",
            "install", "pip", "npm"
        ]
        requires_tools = complexity_level > 1 or any(
            kw in lower_msg for kw in tool_keywords
        )

        intent_type = "tool_execution" if requires_tools else "conversational"
        
        # Select routing paths based on composite attention scoring
        if composite >= 0.85:
            path_selected = "COUNCIL"
        elif composite >= 0.70 or requires_tools or complexity_level > 1 or is_irreversible:
            path_selected = "DEEP"
        elif composite >= 0.40:
            path_selected = "MID"
        else:
            path_selected = "FAST"

        required_confidence = 0.90 if path_selected == "COUNCIL" else (
            0.85 if path_selected == "DEEP" else 0.70
        )

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
            "attention_score": score_obj.to_dict(),
        }
