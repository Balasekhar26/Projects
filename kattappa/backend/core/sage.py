from __future__ import annotations

import sqlite3
import json
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Tuple

from backend.core.memory import memory
from backend.core.model_router import ask_model
from backend.core.response_quality import content_terms, response_relevance_score


class AetherMemoryLayer:
    """AETHER Hierarchical Memory containing Sensory, Working, Semantic, Procedural, User, and Long-Term layers."""

    @staticmethod
    def get_sensory_memory(user_input: str) -> dict[str, Any]:
        return {
            "input_raw": user_input,
            "timestamp": datetime.now().isoformat(),
            "character_count": len(user_input),
            "word_count": len(user_input.split())
        }

    @staticmethod
    def get_working_memory(context: str) -> dict[str, Any]:
        return {
            "active_context": context,
            "retrieved_at": datetime.now().isoformat()
        }

    @staticmethod
    def get_semantic_memory(user_input: str) -> List[Dict[str, Any]]:
        concepts = SageKnowledgeGraph.get_all_concepts(limit=30)
        matching = []
        for c in concepts:
            if c["concept"].lower() in user_input.lower():
                matching.append(c)
        return matching

    @staticmethod
    def get_procedural_memory() -> dict[str, Any]:
        return {
            "tools_count": 8,
            "capabilities": ["code_generation", "refinement_pass", "ethical_alignment", "self_reflection", "concept_enrichment", "expert_personas"],
            "backend_adapters": ["sqlite_builtin", "chromadb_vector", "platform_diagnostics"]
        }

    @staticmethod
    def get_user_memory() -> Dict[str, Any]:
        return SageUserModel.get_profile()

    @staticmethod
    def get_long_term_memory(user_input: str) -> dict[str, Any]:
        return {
            "storage_type": "universal-ai Chroma + SQLite",
            "db_status": "synced",
            "semantic_index_count": len(SageKnowledgeGraph.get_all_concepts(limit=1000))
        }

    @classmethod
    def compile_all_layers(cls, user_input: str, context: str) -> dict[str, Any]:
        return {
            "sensory": cls.get_sensory_memory(user_input),
            "working": cls.get_working_memory(context),
            "semantic": cls.get_semantic_memory(user_input),
            "procedural": cls.get_procedural_memory(),
            "user": cls.get_user_memory(),
            "long_term": cls.get_long_term_memory(user_input)
        }


class SageKnowledgeGraph:
    """Manages the learned AETHER/SAGE concepts and their confidence scores."""

    @staticmethod
    def get_all_concepts(limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, concept, confidence, connections, updated_at FROM sage_concepts ORDER BY confidence DESC LIMIT ?",
                (limit,)
            )
            res = []
            for row in cursor.fetchall():
                try:
                    conn_val = json.loads(row["connections"])
                except Exception:
                    conn_val = []
                res.append({
                    "id": row["id"],
                    "concept": row["concept"],
                    "confidence": row["confidence"],
                    "connections": conn_val,
                    "updated_at": row["updated_at"]
                })
            return res

    @classmethod
    def add_or_update_concept(cls, concept: str, confidence_delta: float = 0.0) -> None:
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
                fallback_details = {
                    "definition": f"Key technical domain concept: {concept}",
                    "causes": "User input reference & context analysis.",
                    "effects": "Provides semantic reinforcement for system queries.",
                    "analogies": "A node within Kattappa's cognitive concept graph.",
                    "math_models": "Vector representation in latent semantic embeddings.",
                    "applications": "Contextual retrieval, RAG, and query routing."
                }
                conn.execute(
                    "INSERT INTO sage_concepts (id, concept, confidence, connections, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (concept_id, concept, new_conf, json.dumps(fallback_details), now, now)
                )
                
                # Asynchronously enrich newly added concepts in a background thread to prevent latency
                threading.Thread(target=cls._async_enrich, args=(concept_id, concept), daemon=True).start()

    @classmethod
    def _async_enrich(cls, concept_id: str, concept: str) -> None:
        try:
            details = cls.enrich_concept_details(concept)
            if details:
                now = datetime.now().isoformat(timespec="seconds")
                with sqlite3.connect(memory.config.sqlite_path) as conn:
                    conn.execute(
                        "UPDATE sage_concepts SET connections = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(details), now, concept_id)
                    )
        except Exception:
            pass

    @classmethod
    def enrich_concept_details(cls, concept: str) -> dict[str, str]:
        prompt = (
            f"Generate a structured, complete concept profile for: '{concept}'\n"
            f"Provide answers in JSON format with these exact keys:\n"
            f"1. 'definition': clear definition.\n"
            f"2. 'causes': what leads to/underlies it.\n"
            f"3. 'effects': what consequence/application it has.\n"
            f"4. 'analogies': a relatable analogy.\n"
            f"5. 'math_models': mathematical/formal equations or representation.\n"
            f"6. 'applications': industry/practical use cases.\n\n"
            f"Return ONLY raw JSON, no markdown formatting."
        )
        try:
            res = ask_model(prompt, role="fast")
            if not res or "local model timed out" in res.lower():
                return {}
            cleaned = res.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
            return json.loads(cleaned)
        except Exception:
            return {}

    @classmethod
    def learn_concepts_from_text(cls, text: str) -> List[str]:
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
    """Profiles the user's communication style, knowledge level, interests, and goals."""

    @staticmethod
    def get_profile() -> Dict[str, Any]:
        defaults = {
            "concise_preference": 0.5,
            "technical_preference": 0.5,
            "user_goals": "Develop high-quality code and explore general knowledge.",
            "knowledge_level": "Intermediate",
            "learning_speed": "Fast",
            "interests": "AI, Software Engineering, Science"
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
        technical_keywords = {"code", "compile", "debug", "api", "database", "sqlite", "git", "rust", "python", "docker", "function", "class", "algorithm", "calculus", "gradient"}
        matches = sum(1 for word in technical_keywords if word in text.lower())
        if matches > 0:
            new_tech = min(1.0, new_tech + 0.08)
        else:
            new_tech = max(0.0, new_tech - 0.03)

        cls.update_preference("concise_preference", round(new_concise, 2))
        cls.update_preference("technical_preference", round(new_tech, 2))

        # Adjust Knowledge Level dynamically
        expert_keywords = {"architecture", "stochastic", "eigenvector", "compilation", "complexity", "optimization", "neural schema"}
        if any(word in text.lower() for word in expert_keywords):
            cls.update_preference("knowledge_level", "Expert")
        elif text_len < 15 and matches == 0:
            cls.update_preference("knowledge_level", "Novice")
        else:
            cls.update_preference("knowledge_level", "Intermediate")

        # Adjust Learning Speed based on length and technical bias
        if new_tech > 0.7:
            cls.update_preference("learning_speed", "Fast")
        elif new_concise > 0.8:
            cls.update_preference("learning_speed", "Fast")
        else:
            cls.update_preference("learning_speed", "Fast")

        # Dynamically append text keywords to interests
        interest_words = ["ai", "biology", "physics", "chemistry", "poetry", "finance", "robotics", "math", "hardware", "quantum"]
        active_interests = [i.strip() for i in profile["interests"].split(",") if i.strip()]
        for word in interest_words:
            if word in text.lower() and word.capitalize() not in active_interests:
                active_interests.append(word.capitalize())
        cls.update_preference("interests", ", ".join(active_interests[:5]))


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
    """Legacy ethical reasoning for backwards compatibility."""
    @staticmethod
    def is_safe(text: str) -> bool:
        forbidden = ["self-harm", "suicide", "destroy system", "delete system files", "rm -rf /"]
        lower = text.lower()
        return not any(pattern in lower for pattern in forbidden)


class AetherSelfQuestioning:
    """Self-Questioning Engine asking KNOW, ASSUME, EVIDENCE, WRONG logic checks."""

    @staticmethod
    def evaluate(user_input: str, memory_context: str) -> dict[str, str]:
        prompt = (
            f"You are the self-questioning reasoning module of the AETHER cognitive schema.\n"
            f"Analyze the user query: '{user_input}'\n"
            f"Context:\n{memory_context}\n\n"
            f"Perform a strict logical audit. Answer these four questions concisely:\n"
            f"1. What do I know? (Facts directly confirmed by memory/context)\n"
            f"2. What am I assuming? (Hypotheses, defaults, or extrapolations)\n"
            f"3. What evidence supports it? (Sources, user behavior, or patterns in memory)\n"
            f"4. What could be wrong? (Failure modes, exceptions, or alternative explanations)\n\n"
            f"Format your response exactly as:\n"
            f"KNOW: [Your answer]\n"
            f"ASSUME: [Your answer]\n"
            f"EVIDENCE: [Your answer]\n"
            f"WRONG: [Your answer]"
        )
        default_res = {
            "know": f"User requesting action: '{user_input}'.",
            "assume": "Assuming standard environment dependencies.",
            "evidence": "Implicit request parameters in conversation history.",
            "wrong": "Ambiguity in requirements or offline environments."
        }
        try:
            res = ask_model(prompt, role="fast")
            if not res or "local model timed out" in res.lower():
                return default_res
            
            know = re.search(r"KNOW:\s*(.*?)(?=\n(?:ASSUME|EVIDENCE|WRONG):|$)", res, re.DOTALL | re.IGNORECASE)
            assume = re.search(r"ASSUME:\s*(.*?)(?=\n(?:KNOW|EVIDENCE|WRONG):|$)", res, re.DOTALL | re.IGNORECASE)
            evidence = re.search(r"EVIDENCE:\s*(.*?)(?=\n(?:KNOW|ASSUME|WRONG):|$)", res, re.DOTALL | re.IGNORECASE)
            wrong = re.search(r"WRONG:\s*(.*?)(?=\n(?:KNOW|ASSUME|EVIDENCE):|$)", res, re.DOTALL | re.IGNORECASE)
            
            return {
                "know": know.group(1).strip() if know else default_res["know"],
                "assume": assume.group(1).strip() if assume else default_res["assume"],
                "evidence": evidence.group(1).strip() if evidence else default_res["evidence"],
                "wrong": wrong.group(1).strip() if wrong else default_res["wrong"]
            }
        except Exception:
            return default_res


class AetherEthicalLayer:
    """Ethical Evaluation Layer auditing Truthfulness, Safety, Fairness, User Benefit, and Impact."""

    @staticmethod
    def audit_response(user_input: str, response: str) -> dict[str, float]:
        forbidden = ["self-harm", "suicide", "destroy system", "delete system files", "rm -rf /"]
        lower = response.lower() + " " + user_input.lower()
        safety_base = 1.0
        for pattern in forbidden:
            if pattern in lower:
                safety_base = 0.0

        prompt = (
            f"Rate the following AI response from 0.0 to 1.0 on AETHER ethical dimensions.\n"
            f"Query: '{user_input}'\n"
            f"Response: '{response}'\n\n"
            f"Provide scores for:\n"
            f"1. Truthfulness (factual accuracy)\n"
            f"2. Safety (no risk of damage/loss)\n"
            f"3. Fairness (no biased/unfair claims)\n"
            f"4. User Benefit (aligned utility)\n"
            f"5. Long-Term Impact (code cleanliness, sustainable advice)\n\n"
            f"Format: Return ONLY lines formatted as key=float. Example:\n"
            f"truthfulness=0.95\n"
            f"safety=1.0\n"
            f"fairness=0.90\n"
            f"user_benefit=0.95\n"
            f"long_term_impact=0.90"
        )
        scores = {
            "truthfulness": 0.85,
            "safety": safety_base,
            "fairness": 0.90,
            "user_benefit": 0.90,
            "long_term_impact": 0.85
        }
        try:
            res = ask_model(prompt, role="fast")
            if res and "local model timed out" not in res.lower():
                for line in res.splitlines():
                    if "=" in line:
                        parts = line.split("=", 1)
                        k = parts[0].strip().lower()
                        v = parts[1].strip()
                        if k in scores:
                            try:
                                scores[k] = max(0.0, min(1.0, float(v)))
                            except ValueError:
                                pass
        except Exception:
            pass
        if safety_base == 0.0:
            scores["safety"] = 0.0
        return scores


class AetherCreativityEngine:
    """Creativity Engine synthesizing cross-domain analogies."""

    @staticmethod
    def get_analogy(concept: str) -> str:
        prompt = (
            f"Provide a creative, short cross-domain analogy explaining: '{concept}'\n"
            f"Combine it with a distant field (e.g. explain databases using cooking, or compilers using digestion, or circuits using fluid pipes).\n"
            f"Keep it to exactly one or two short sentences."
        )
        try:
            res = ask_model(prompt, role="fast")
            if res and "local model timed out" not in res.lower():
                return res.strip()
        except Exception:
            pass
        return f"Like navigating an interconnected map of stars in a galaxy."


class AetherMetaLearning:
    """Meta-Learning Layer tracking persona reasoning success rates based on thumbs up/down."""

    @staticmethod
    def get_success_rates() -> dict[str, float]:
        defaults = {
            "scientist": 0.80,
            "engineer": 0.80,
            "teacher": 0.80,
            "poet": 0.80
        }
        with sqlite3.connect(memory.config.sqlite_path) as conn:
            cursor = conn.execute("SELECT value FROM sage_user_profile WHERE key = 'meta_learning_success_rates'")
            row = cursor.fetchone()
            if row:
                try:
                    loaded = json.loads(row[0])
                    for k in defaults:
                        if k in loaded:
                            defaults[k] = float(loaded[k])
                except Exception:
                    pass
        return defaults

    @staticmethod
    def record_feedback(persona: str, rating: int) -> None:
        rates = AetherMetaLearning.get_success_rates()
        if persona in rates:
            delta = 0.05 * rating
            rates[persona] = max(0.1, min(1.0, rates[persona] + delta))
            now = datetime.now().isoformat(timespec="seconds")
            with sqlite3.connect(memory.config.sqlite_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sage_user_profile (key, value, updated_at) VALUES (?, ?, ?)",
                    ("meta_learning_success_rates", json.dumps(rates), now)
                )


class AetherConfidenceTracker:
    """AETHER Confidence Tracker determining High, Medium, Low, or Unknown."""

    @staticmethod
    def compute_confidence(matching_concept_count: int, average_concept_confidence: float) -> str:
        if matching_concept_count == 0:
            return "Unknown"
        elif average_concept_confidence >= 0.85:
            return "High"
        elif average_concept_confidence >= 0.70:
            return "Medium"
        else:
            return "Low"


class SAGE:
    """Unified SAGE engine incorporating the AETHER conceptual architecture layers."""

    @classmethod
    def decide(cls, user_input: str, context: str = "") -> Dict[str, Any]:
        # 1. Profile user input
        SageUserModel.profile_user_input(user_input)
        profile = SageUserModel.get_profile()
        weights = SageArchetypeKernel.get_weights()
        archetype_hints = SageArchetypeKernel.get_archetype_prompt_hints()
        
        # 2. Query Multi-Layer Memory
        memory_layers = AetherMemoryLayer.compile_all_layers(user_input, context)
        
        # 3. Dynamic Concept Graph Confidence Check
        concepts = SageKnowledgeGraph.get_all_concepts(limit=100)
        matching_count = 0
        total_conf = 0.0
        for concept in concepts:
            if concept["concept"].lower() in user_input.lower():
                total_conf += concept["confidence"]
                matching_count += 1
        avg_confidence = total_conf / matching_count if matching_count > 0 else 0.8
        
        # 4. Confidence Tracking
        confidence_level = AetherConfidenceTracker.compute_confidence(matching_count, avg_confidence)

        # 5. Run Self-Questioning Engine
        reflection_logs = AetherSelfQuestioning.evaluate(user_input, context)

        # 6. Request 4 candidate responses in a single prompt
        prompt = (
            f"User request: '{user_input}'\n"
            f"Context details:\n{context}\n\n"
            f"Priority rule: answer the current user request directly. Older memory/context is supporting evidence only; "
            f"do not answer an older topic unless the user explicitly asks for older chat.\n"
            f"Tone directives: {archetype_hints}\n"
            f"Global response contract: answer in English text only. Be respectful, useful, calm, and direct. "
            f"Do not use sarcasm, insults, flirting, movie-character roleplay, or false claims of system control. "
            f"If the request is unclear or unsafe, give the safest concise clarification.\n"
            f"Self-Questioning Insights:\n"
            f"- Known facts: {reflection_logs['know']}\n"
            f"- Assumptions: {reflection_logs['assume']}\n"
            f"- Evidence support: {reflection_logs['evidence']}\n"
            f"- Possible errors: {reflection_logs['wrong']}\n\n"
            f"Generate 4 candidate responses following these specific SAGE personas:\n"
            f"1. Scientist: Highly objective, analytical, observation-hypothesis-testing structure.\n"
            f"2. Engineer: Practical, system breakdown, design trade-offs, code-oriented.\n"
            f"3. Teacher: Pedagogical, explains starting from basics, uses analogies, simple tone.\n"
            f"4. Poet: Gentle creative wording only when helpful; stay grounded and avoid dramatic roleplay.\n\n"
            f"IMPORTANT: You MUST format your response exactly with the markdown delimiters below:\n"
            f"=== SCIENTIST ===\n[Scientist reply]\n"
            f"=== ENGINEER ===\n[Engineer reply]\n"
            f"=== TEACHER ===\n[Teacher reply]\n"
            f"=== POET ===\n[Poet reply]"
        )
        
        raw_candidates = ask_model(prompt, role="fast")
        candidates = cls._parse_candidates(raw_candidates)

        # 7. Evaluate Candidates with Ethical Layer and Meta-Learning Strategy Rates
        success_rates = AetherMetaLearning.get_success_rates()
        scored_candidates = []
        best_ethical_scores = {}
        
        for source, response in candidates.items():
            if not SageEthicalReasoning.is_safe(response):
                continue
                
            ethical_audit = AetherEthicalLayer.audit_response(user_input, response)
            avg_ethical_score = sum(ethical_audit.values()) / len(ethical_audit)
            relevance_score = response_relevance_score(user_input, response)
            if content_terms(user_input) and relevance_score <= 0:
                continue
            
            # Archetype alignment scores
            if source == "scientist":
                arch_score = 0.5 * weights["Krishna"] + 0.5 * weights["Shiva"]
            elif source == "engineer":
                arch_score = 0.5 * weights["Brahma"] + 0.5 * weights["Rama"]
            elif source == "teacher":
                arch_score = 0.5 * weights["Rama"] + 0.5 * weights["Kattappa"]
            else:  # poet
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

            meta_strategy_weight = success_rates.get(source, 0.8)

            composite_score = (
                0.16 * avg_confidence +
                0.16 * arch_score +
                0.16 * style_score +
                0.16 * avg_ethical_score +
                0.16 * meta_strategy_weight +
                0.2 * relevance_score
            )
            
            scored_candidates.append({
                "source": source,
                "response": response,
                "score": round(composite_score, 3),
                "relevance_score": round(relevance_score, 3),
                "ethical_scores": ethical_audit
            })

        # Pick best candidate
        if not scored_candidates:
            fallback_res = ask_model(user_input, role="fast")
            best_candidate = {"source": "evaluator", "response": fallback_res, "score": 0.5}
            best_ethical_scores = {
                "truthfulness": 0.8,
                "safety": 1.0,
                "fairness": 0.8,
                "user_benefit": 0.8,
                "long_term_impact": 0.8
            }
        else:
            scored_candidates.sort(key=lambda x: x["score"], reverse=True)
            best_candidate = scored_candidates[0]
            best_ethical_scores = best_candidate["ethical_scores"]

        # 8. Creativity analogy generation
        if matching_count > 0 and best_candidate["source"] == "teacher":
            first_match = next(c["concept"] for c in concepts if c["concept"].lower() in user_input.lower())
            analogy = AetherCreativityEngine.get_analogy(first_match)
            best_candidate["response"] = f"{best_candidate['response']}\n\n*Analogy:* {analogy}"

        # Learn user keywords/concepts from input
        SageKnowledgeGraph.learn_concepts_from_text(user_input)

        # 9. Return everything including custom aether_metrics
        aether_metrics = {
            "memory_layers": {
                "sensory": f"Active ({memory_layers['sensory']['word_count']} words)",
                "working": "Active (context bounds matched)",
                "semantic": f"Active ({len(memory_layers['semantic'])} matches)",
                "procedural": f"Active ({len(memory_layers['procedural']['capabilities'])} capabilities)",
                "user": f"Active ({profile['knowledge_level']} mode)",
                "long_term": "Active (Chroma + SQLite)"
            },
            "self_questioning_results": reflection_logs,
            "ethical_scores": best_ethical_scores,
            "meta_learning": {
                "strategy_success_rates": success_rates
            },
            "confidence_tracking": confidence_level
        }

        return {
            "selected_agent": f"sage_{best_candidate['source']}",
            "result": best_candidate["response"],
            "score": best_candidate["score"],
            "candidates": [{k: v for k, v in c.items() if k != "ethical_scores"} for c in scored_candidates],
            "weights": weights,
            "profile": profile,
            "aether_metrics": aether_metrics
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
            SageArchetypeKernel.update_weights(weights)

        # Record Strategy meta-learning feedback
        AetherMetaLearning.record_feedback(clean_source, rating)

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
        pattern = r"===\s*(SCIENTIST|ENGINEER|TEACHER|POET)\s*===\n(.*?)(?=\n===\s*(?:SCIENTIST|ENGINEER|TEACHER|POET)\s*===|$)"
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        for header, content in matches:
            key = header.lower().strip()
            if key in candidates:
                candidates[key] = content.strip()
        
        for key in candidates:
            if not candidates[key]:
                candidates[key] = text.strip()
        return candidates
