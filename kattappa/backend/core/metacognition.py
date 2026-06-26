"""Metacognitive Gate (Layer 7B).

Evaluates grounding of reasoning/responses and outputs cognitive routing decisions.
"""

from __future__ import annotations

import json
from typing import Any, Dict
from backend.core.model_router import ask_model


class MetacognitiveGate:
    @classmethod
    def verify_grounding(cls, state: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 7B: Verify response grounding and determine the next cognitive action."""
        user_input = state.get("user_input", "")
        memory_context = state.get("memory_context") or "None"
        candidate_result = state.get("result") or ""

        memory_confidence = state.get("memory_confidence_level", "HIGH")
        confidence_warning = ""
        if memory_confidence == "LOW":
            confidence_warning = "\n[WARNING: Memory database query timed out or failed. Context is unreliable/empty. Confidence is LOW. You must recommend RE_RETRIEVE, SEARCH, or ASK_CLARIFICATION rather than ANSWERing directly.]\n"

        # Construct prompt for the local fast model to act as a metacognitive arbiter
        if not candidate_result:
            prompt = (
                "You are the Kattappa Metacognitive Gate. Analyze the user request and retrieved memory context.\n\n"
                f"User Request: {user_input}\n\n"
                f"Retrieved Memory Context:\n{memory_context}\n\n"
                f"{confidence_warning}"
                "Decide the best cognitive action. Choose exactly one of these actions:\n"
                "- ANSWER: If the query is simple and we have sufficient information to answer directly.\n"
                "- SEARCH: If the query requires external information / web search to be resolved.\n"
                "- TOOL: If the query requires executing a specific system tool (e.g. file edit, terminal run).\n"
                "- CALCULATE: If the query requires executing code to perform math/calculations.\n"
                "- ASK_CLARIFICATION: If the query is highly ambiguous and requires asking the user for details.\n"
                "- ABSTAIN: If we cannot answer or perform the task safely.\n"
                "- RE_RETRIEVE: If we have chat sessions or memories but need to search them again with a different query.\n\n"
                "Return ONLY a JSON object in this format:\n"
                "{\n"
                '  "grounded": true,\n'
                '  "confidence": 0.9,\n'
                '  "recommended_action": "ANSWER" | "SEARCH" | "TOOL" | "CALCULATE" | "ASK_CLARIFICATION" | "ABSTAIN" | "RE_RETRIEVE",\n'
                '  "new_search_query": "string or null",\n'
                '  "reason": "explanation of decision"\n'
                "}"
            )
        else:
            prompt = (
                "You are the Kattappa Metacognitive Gate. Verify if the draft response is grounded in the retrieved memory context.\n\n"
                f"User Request: {user_input}\n\n"
                f"Retrieved Memory Context:\n{memory_context}\n\n"
                f"Draft Response: {candidate_result}\n\n"
                f"{confidence_warning}"
                "Evaluate if the draft response contains hallucinations, ungrounded assertions, or if it is fully supported by the memory context.\n"
                "Choose exactly one of these actions:\n"
                "- ANSWER: If the response is grounded and correct.\n"
                "- ASK_CLARIFICATION: If the response is uncertain or requires clarification.\n"
                "- RE_RETRIEVE: If the response lacks factual support that might be found by searching memory again with a different query.\n"
                "- SEARCH: If the response lacks factual support that needs web search.\n"
                "- ABSTAIN: If the response is ungrounded and cannot be verified.\n\n"
                "Return ONLY a JSON object in this format:\n"
                "{\n"
                '  "grounded": true,\n'
                '  "confidence": 0.9,\n'
                '  "recommended_action": "ANSWER" | "ASK_CLARIFICATION" | "RE_RETRIEVE" | "SEARCH" | "ABSTAIN",\n'
                '  "new_search_query": "string or null",\n'
                '  "reason": "explanation of decision"\n'
                "}"
            )

        try:
            raw_res = ask_model(prompt, role="fast")
            # Parse JSON safely, stripping markdown block wrappers if present
            cleaned = raw_res.strip()
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1:
                parsed = json.loads(cleaned[start_idx : end_idx + 1])
            else:
                parsed = json.loads(cleaned)
        except Exception as e:
            # Safe default fallback
            parsed = {
                "grounded": True,
                "confidence": 0.5,
                "recommended_action": "ANSWER",
                "new_search_query": None,
                "reason": f"Metacognitive parsing fallback: {e}",
            }

        return parsed
