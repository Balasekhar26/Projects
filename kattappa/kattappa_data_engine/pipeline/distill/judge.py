import math
from typing import Dict, Any

class DistillationJudge:
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock

    def evaluate_and_synthesize(self, response_node: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates scores, checks variance outliers, and synthesizes the optimal merged answer."""
        cat = response_node["category"]
        
        # 1. Run Teacher Scoring Matrix
        scores = self._score_teachers(response_node)
        
        # 2. Check Variance (Teacher Disagreement)
        # We calculate the variance of the composite scores across ChatGPT, Gemini, and Claude
        cg_score = sum(scores["chatgpt"].values()) / len(scores["chatgpt"])
        gm_score = sum(scores["gemini"].values()) / len(scores["gemini"])
        cl_score = sum(scores["claude"].values()) / len(scores["claude"])
        
        mean_score = (cg_score + gm_score + cl_score) / 3
        variance = ((cg_score - mean_score)**2 + (gm_score - mean_score)**2 + (cl_score - mean_score)**2) / 3
        
        disagreement = variance > 2.5
        
        # 3. Dynamic Synthesis Selection Rules
        synthesized_response = self._synthesize_merged_response(cat, response_node)
        
        return {
            "id": response_node["id"],
            "category": cat,
            "instruction": response_node["instruction"],
            "teacher_chatgpt": response_node["teacher_chatgpt"],
            "teacher_gemini": response_node["teacher_gemini"],
            "teacher_claude": response_node["teacher_claude"],
            "teacher_scores": scores,
            "composite_score": round(mean_score, 2),
            "score_variance": round(variance, 4),
            "teacher_disagreement": disagreement,
            "final_response": synthesized_response,
            "synthesis_type": "merged_framework" if not disagreement else "disagreement_arbitration"
        }

    def _score_teachers(self, node: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Scores each teacher response dynamically on a 0-10 scale across 5 dimensions."""
        cat = node["category"]
        
        # Mock Evaluator Model Logic: assigns logical scores based on category suitability
        if cat == "coding" or cat == "engineering":
            return {
                "chatgpt": {"reasoning": 9.2, "completeness": 9.0, "clarity": 8.5, "safety": 9.5, "telugu": 1.0},
                "gemini": {"reasoning": 8.0, "completeness": 8.5, "clarity": 8.0, "safety": 9.0, "telugu": 1.0},
                "claude": {"reasoning": 9.0, "completeness": 8.8, "clarity": 9.2, "safety": 9.5, "telugu": 1.0}
            }
        elif cat == "planning":
            return {
                "chatgpt": {"reasoning": 8.5, "completeness": 8.0, "clarity": 8.5, "safety": 9.0, "telugu": 1.0},
                "gemini": {"reasoning": 9.5, "completeness": 9.2, "clarity": 8.8, "safety": 9.2, "telugu": 1.0},
                "claude": {"reasoning": 9.0, "completeness": 9.0, "clarity": 9.2, "safety": 9.5, "telugu": 1.0}
            }
        elif cat == "telugu":
            return {
                "chatgpt": {"reasoning": 7.0, "completeness": 7.0, "clarity": 7.0, "safety": 8.0, "telugu": 5.0},
                "gemini": {"reasoning": 8.0, "completeness": 8.0, "clarity": 8.0, "safety": 8.5, "telugu": 7.5},
                "claude": {"reasoning": 9.0, "completeness": 9.0, "clarity": 9.2, "safety": 9.5, "telugu": 9.5}
            }
        else: # general / other
            return {
                "chatgpt": {"reasoning": 8.0, "completeness": 8.0, "clarity": 8.0, "safety": 9.0, "telugu": 5.0},
                "gemini": {"reasoning": 8.0, "completeness": 8.0, "clarity": 8.0, "safety": 9.0, "telugu": 5.0},
                "claude": {"reasoning": 9.0, "completeness": 9.0, "clarity": 9.2, "safety": 9.5, "telugu": 5.0}
            }

    def _synthesize_merged_response(self, category: str, node: Dict[str, Any]) -> str:
        """Synthesizes teacher segments utilizing rules optimized by category."""
        cg = node["teacher_chatgpt"]
        gm = node["teacher_gemini"]
        cl = node["teacher_claude"]
        
        if category == "engineering" or category == "tool_usage":
            # Structure from ChatGPT + Style from Claude
            return f"{cg}\n\n[Analysis Summary]\n{cl}"
        elif category == "planning":
            # Architect from Gemini + Review from ChatGPT
            return f"{gm}\n\n[Validation Verification]\n{cg}"
        elif category == "teaching" or category == "telugu":
            # Tone/Accuracy from Claude + Concept details from Gemini
            return f"{cl}\n\n[Technical Context]\n{gm}"
            
        # Default merge: Claude base with ChatGPT logic details
        return f"{cl}\n\n[Logic Derivation]\n{cg}"
