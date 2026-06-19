from __future__ import annotations

import sqlite3
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from backend.core.memory import memory
from backend.core.model_router import ask_model


class SageKnowledgeGraph:
    """Manages the learned SAGE concepts and their confidence scores."""

    @staticmethod
    def get_all_concepts(limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, concept, confidence, connections, updated_at FROM sage_concepts ORDER BY confidence DESC LIMIT ?",
                (limit,)
            )
            return [
                {
                    "id": row["id"],
                    "concept": row["concept"],
                    "confidence": row["confidence"],
                    "connections": json.loads(row["connections"]),
                    "updated_at": row["updated_at"]
                }
                for row in cursor.fetchall()
            ]

    @staticmethod
    def add_or_update_concept(concept: str, confidence_delta: float = 0.0) -> None:
        concept = concept.strip()
        if not concept:
            return
        concept_id = concept.lower().replace(" ", "_")
        now = datetime.now().isoformat(timespec="seconds")
        
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            cursor = conn.execute("SELECT confidence, connections FROM sage_concepts WHERE id = ?", (concept_id,))
            row = cursor.fetchone()
            if row:
                old_conf = row[0]
                new_conf = max(0.0, min(1.0, old_conf + confidence_delta))
                conn.execute(
                    "UPDATE sage_concepts SET confidence = ?, updated_at = ? WHERE id = ?",
                    (new_conf, now, concept_id)
                )
            else:
                new_conf = max(0.0, min(1.0, 0.8 + confidence_delta))
                conn.execute(
                    "INSERT INTO sage_concepts (id, concept, confidence, connections, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (concept_id, concept, new_conf, json.dumps([]), now, now)
                )

    @classmethod
    def learn_concepts_from_text(cls, text: str) -> List[str]:
        """Extracts and updates concepts from text using the LLM in a simple prompt."""
        prompt = (
            f"Extract a comma-separated list of key technical, scientific, or domain-specific concepts mentioned in this text.\n"
            f"Format: concept1, concept2, concept3\n"
            f"Only return the comma-separated list and nothing else.\n\n"
            f"Text:\n{text}"
        )
        try:
            res = ask_model(prompt, role="fast")
            if not res or "local model timed out" in res.lower():
                return []
            extracted = [c.strip() for c in res.split(",") if c.strip()]
            for concept in extracted:
                cls.add_or_update_concept(concept, confidence_delta=0.01)
            return extracted
        except Exception:
            return []


class SageUserModel:
    """Profiles the user's communication style and interests."""

    @staticmethod
    def get_profile() -> Dict[str, Any]:
        defaults = {
            "concise_preference": 0.5,
            "technical_preference": 0.5,
            "user_goals": "Develop high-quality code and explore general knowledge."
        }
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            cursor = conn.execute("SELECT key, value FROM sage_user_profile")
            rows = cursor.fetchall()
            for key, val in rows:
                if key in {"concise_preference", "technical_preference"}:
                    try:
                        defaults[key] = float(val)
                    except ValueError:
                        pass
                else:
                    defaults[key] = val
        return defaults

    @staticmethod
    def update_preference(key: str, value: Any) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sage_user_profile (key, value, updated_at) VALUES (?, ?, ?)",
                (key, str(value), now)
            )

    @classmethod
    def profile_user_input(cls, text: str) -> None:
        """Adapts user preferences based on current message style."""
        profile = cls.get_profile()
        text_len = len(text)
        
        # Adjust concise preference
        new_concise = profile["concise_preference"]
        if text_len < 20:
            new_concise = min(1.0, new_concise + 0.05)
        elif text_len > 150:
            new_concise = max(0.0, new_concise - 0.05)
            
        # Adjust technical preference
        new_tech = profile["technical_preference"]
        technical_keywords = {"code", "compile", "debug", "api", "database", "sqlite", "git", "rust", "python", "docker", "function", "class"}
        matches = sum(1 for word in technical_keywords if word in text.lower())
        if matches > 0:
            new_tech = min(1.0, new_tech + 0.08)
        else:
            new_tech = max(0.0, new_tech - 0.03)

        cls.update_preference("concise_preference", round(new_concise, 2))
        cls.update_preference("technical_preference", round(new_tech, 2))


class SageArchetypeKernel:
    """Manages weights of Rama, Krishna, Brahma, Shiva, Kattappa archetypes."""

    @staticmethod
    def get_weights() -> Dict[str, float]:
        weights = {"Rama": 0.2, "Krishna": 0.2, "Brahma": 0.2, "Shiva": 0.2, "Kattappa": 0.2}
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            cursor = conn.execute("SELECT name, weight FROM sage_archetypes")
            for name, weight in cursor.fetchall():
                if name in weights:
                    weights[name] = float(weight)
        return weights

    @staticmethod
    def update_weights(weights: Dict[str, float]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        # Normalize weights so they sum to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            for name, weight in weights.items():
                conn.execute(
                    "UPDATE sage_archetypes SET weight = ?, updated_at = ? WHERE name = ?",
                    (round(weight, 3), now, name)
                )

    @classmethod
    def get_archetype_prompt_hints(cls) -> str:
        weights = cls.get_weights()
        hints = []
        if weights["Rama"] > 0.25:
            hints.append("Maintain strict integrity, keeping commitments and prioritizing honesty.")
        if weights["Krishna"] > 0.25:
            hints.append("Incorporate strategic wisdom, thinking several steps ahead and analyzing trade-offs.")
        if weights["Brahma"] > 0.25:
            hints.append("Show high creativity and explore innovative ideas.")
        if weights["Shiva"] > 0.25:
            hints.append("Strive for balance, risk mitigation, and structural stability.")
        if weights["Kattappa"] > 0.25:
            hints.append("Maintain deep loyalty to the user's goals, acting as a dedicated assistant.")
        return " ".join(hints)


class SageEthicalReasoning:
    """Performs safety and ethical alignment checks."""

    @staticmethod
    def is_safe(text: str) -> bool:
        forbidden = ["self-harm", "suicide", "destroy system", "delete system files", "rm -rf /"]
        lower = text.lower()
        for pattern in forbidden:
            if pattern in lower:
                return False
        return True


class SAGE:
    """Unified SAGE engine."""

    @classmethod
    def decide(cls, user_input: str, context: str = "") -> Dict[str, Any]:
        # 1. Update user profile based on incoming input
        SageUserModel.profile_user_input(user_input)
        profile = SageUserModel.get_profile()
        weights = SageArchetypeKernel.get_weights()
        archetype_hints = SageArchetypeKernel.get_archetype_prompt_hints()
        
        # 2. Extract context concepts to find knowledge graph confidence score
        concepts = SageKnowledgeGraph.get_all_concepts(limit=100)
        matching_confidence = 0.8
        matching_count = 0
        total_conf = 0.0
        for concept in concepts:
            if concept["concept"].lower() in user_input.lower():
                total_conf += concept["confidence"]
                matching_count += 1
        if matching_count > 0:
            matching_confidence = total_conf / matching_count

        # 3. Request 4 candidate responses in a single LLM request (optimized for local speed)
        prompt = (
            f"User request: '{user_input}'\n"
            f"Context details:\n{context}\n\n"
            f"Tone directives: {archetype_hints}\n"
            f"Generate 4 candidate responses following these specific SAGE personas:\n"
            f"1. Scientist: Highly objective, analytical, observation-hypothesis-testing structure.\n"
            f"2. Engineer: Practical, system breakdown, design trade-offs, code-oriented.\n"
            f"3. Teacher: Pedagogical, explains starting from basics, uses analogies, simple tone.\n"
            f"4. Poet: Symbolical, narrative, creative metaphors, blends art with science.\n\n"
            f"IMPORTANT: You MUST format your response exactly with the markdown delimiters below:\n"
            f"=== SCIENTIST ===\n[Scientist reply]\n"
            f"=== ENGINEER ===\n[Engineer reply]\n"
            f"=== TEACHER ===\n[Teacher reply]\n"
            f"=== POET ===\n[Poet reply]"
        )
        
        raw_candidates = ask_model(prompt, role="fast")
        candidates = cls._parse_candidates(raw_candidates)

        # 4. Evaluate candidates
        scored_candidates = []
        for source, response in candidates.items():
            if not SageEthicalReasoning.is_safe(response):
                continue
            
            # Archetype alignment scores
            if source == "scientist":
                # Aligns with Krishna (Wisdom) and Shiva (Balance)
                arch_score = 0.5 * weights["Krishna"] + 0.5 * weights["Shiva"]
            elif source == "engineer":
                # Aligns with Brahma (Creation) and Rama (Duty)
                arch_score = 0.5 * weights["Brahma"] + 0.5 * weights["Rama"]
            elif source == "teacher":
                # Aligns with Rama (Duty) and Kattappa (Loyalty)
                arch_score = 0.5 * weights["Rama"] + 0.5 * weights["Kattappa"]
            else:  # poet
                # Aligns with Brahma (Creation)
                arch_score = 0.8 * weights["Brahma"] + 0.2 * weights["Krishna"]

            # Style alignment score
            style_score = 0.5
            res_len = len(response)
            if profile["concise_preference"] > 0.6:
                style_score += 0.3 if res_len < 300 else -0.2
            elif profile["concise_preference"] < 0.4:
                style_score += 0.3 if res_len > 400 else -0.1

            if profile["technical_preference"] > 0.6 and source in {"scientist", "engineer"}:
                style_score += 0.2
            elif profile["technical_preference"] < 0.4 and source == "poet":
                style_score += 0.2

            composite_score = 0.4 * matching_confidence + 0.3 * arch_score + 0.3 * style_score
            scored_candidates.append({
                "source": source,
                "response": response,
                "score": round(composite_score, 3)
            })

        # Pick best candidate
        if not scored_candidates:
            fallback_res = ask_model(user_input, role="fast")
            best_candidate = {"source": "evaluator", "response": fallback_res, "score": 0.5}
        else:
            scored_candidates.sort(key=lambda x: x["score"], reverse=True)
            best_candidate = scored_candidates[0]

        # Learn user keywords/concepts from input asynchronously in the background
        SageKnowledgeGraph.learn_concepts_from_text(user_input)

        return {
            "selected_agent": f"sage_{best_candidate['source']}",
            "result": best_candidate["response"],
            "score": best_candidate["score"],
            "candidates": scored_candidates,
            "weights": weights,
            "profile": profile
        }

    @classmethod
    def learn_from(cls, user_input: str, source: str, rating: int) -> Dict[str, Any]:
        """Runs reflection based on user feedback. rating is 1 (thumbs up) or -1 (thumbs down)."""
        weights = SageArchetypeKernel.get_weights()
        clean_source = source.replace("sage_", "")
        
        # Define which archetypes to reinforce
        reinforcements = {
            "scientist": ["Krishna", "Shiva"],
            "engineer": ["Brahma", "Rama"],
            "teacher": ["Rama", "Kattappa"],
            "poet": ["Brahma"]
        }
        
        target_archs = reinforcements.get(clean_source, [])
        if target_archs:
            delta = 0.05 * rating
            for arch in target_archs:
                weights[arch] = max(0.05, min(0.9, weights[arch] + delta))
            # Normalize and save
            SageArchetypeKernel.update_weights(weights)

        # Update concept confidence levels based on rating
        concepts = SageKnowledgeGraph.get_all_concepts(limit=100)
        confidence_delta = 0.05 * rating
        for concept in concepts:
            if concept["concept"].lower() in user_input.lower():
                SageKnowledgeGraph.add_or_update_concept(concept["concept"], confidence_delta=confidence_delta)

        return {
            "success": True,
            "new_weights": SageArchetypeKernel.get_weights(),
            "rating": rating
        }

    @staticmethod
    def _parse_candidates(text: str) -> Dict[str, str]:
        candidates = {
            "scientist": "",
            "engineer": "",
            "teacher": "",
            "poet": ""
        }
        # Look for headers like === SCIENTIST ===
        pattern = r"===\s*(SCIENTIST|ENGINEER|TEACHER|POET)\s*===\n(.*?)(?=\n===\s*(?:SCIENTIST|ENGINEER|TEACHER|POET)\s*===|$)"
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        for header, content in matches:
            key = header.lower().strip()
            if key in candidates:
                candidates[key] = content.strip()
        
        # Fallback if parsing failed
        for key in candidates:
            if not candidates[key]:
                candidates[key] = text.strip()
        return candidates
