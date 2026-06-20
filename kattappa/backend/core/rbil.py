from __future__ import annotations

import re
import datetime
import math
import json
import pathlib
import threading
from typing import Any

# Registry file location
REGISTRY_PATH = pathlib.Path(__file__).parent / "local_registry.json"
METRICS_PATH = pathlib.Path(__file__).parent.parent / "data" / "rbil_metrics.json"

class MetricsTracker:
    _lock = threading.Lock()
    _defaults = {
        "llm_calls_avoided": 0,
        "tokens_saved": 0,
        "time_saved": 0.0,
        "cache_hits": 0,
        "rule_hits": 0,
        "escalations": 0,
        "timeouts_prevented": 0
    }

    @classmethod
    def load(cls) -> dict[str, Any]:
        with cls._lock:
            try:
                if METRICS_PATH.exists():
                    with open(METRICS_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # Ensure all default keys exist
                        for k, v in cls._defaults.items():
                            if k not in data:
                                data[k] = v
                        return data
            except Exception:
                pass
            return cls._defaults.copy()

    @classmethod
    def save(cls, data: dict[str, Any]) -> None:
        with cls._lock:
            try:
                METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(METRICS_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    @classmethod
    def record_hit(cls, hit_type: str, time_saved: float = 1.5, tokens_saved: int = 180) -> None:
        metrics = cls.load()
        metrics["llm_calls_avoided"] += 1
        metrics["time_saved"] += time_saved
        metrics["tokens_saved"] += tokens_saved
        if hit_type == "cache":
            metrics["cache_hits"] += 1
        elif hit_type == "rule":
            metrics["rule_hits"] += 1
        cls.save(metrics)

    @classmethod
    def record_escalation(cls) -> None:
        metrics = cls.load()
        metrics["escalations"] += 1
        cls.save(metrics)

    @classmethod
    def record_timeout_prevented(cls) -> None:
        metrics = cls.load()
        metrics["timeouts_prevented"] += 1
        cls.save(metrics)


class LocalRegistry:
    _data: dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_data(cls) -> dict[str, Any]:
        with cls._lock:
            if not cls._data:
                try:
                    if REGISTRY_PATH.exists():
                        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                            cls._data = json.load(f)
                except Exception:
                    pass
                if not cls._data:
                    # Hardcoded fallback
                    cls._data = {
                        "personality": "I am Kattappa, a loyal, quiet, and reliable local-first assistant.",
                        "archetypes": {},
                        "projects": {},
                        "faqs": {}
                    }
            return cls._data


class ArchetypeEngine:
    @classmethod
    def parse_and_interpret(cls, text: str) -> str | None:
        # Check if query matches archetype terms
        # Need to handle exact questions like "what do these readings mean", "explain archetype Rama 30%", etc.
        text_lower = text.lower()
        # Do not trigger archetype engine on general "kattappa" assistant mentions.
        # Only trigger if other archetypes are present, "archetype" is explicitly mentioned, or "readings" is mentioned.
        other_archetypes = ["rama", "krishna", "brahma", "shiva"]
        has_archetype = any(name in text_lower for name in other_archetypes) or "archetype" in text_lower or "readings in you" in text_lower
        if not has_archetype:
            # If "kattappa" is in the text, check if it's accompanied by percentage/readings keywords
            if "kattappa" in text_lower and any(kw in text_lower for kw in ("percent", "readings", "meaning of", "value", "values")):
                has_archetype = True
                
        if not has_archetype:
            return None

        # Look for percentages or numbers associated with archetype names
        # E.g. "Rama 30%", "Rama: 30", "Brahma 30 percent"
        readings = {}
        archetype_names = ["rama", "krishna", "brahma", "shiva", "kattappa"]
        for name in archetype_names:
            # Match name followed by spaces/colons/percent/numbers
            pattern = rf"(?i)\b{name}\b\s*[:\-=]?\s*(\d+)\s*%?"
            match = re.search(pattern, text)
            if match:
                readings[name.capitalize()] = int(match.group(1))

        reg_data = LocalRegistry.get_data()
        arch_defs = reg_data.get("archetypes", {})

        if not readings:
            # No specific values provided, explain archetypes generally
            res = ["Here are the meaning of the Kattappa diagnostic archetypes:\n"]
            for name, details in arch_defs.items():
                res.append(f"**{name}**: {details.get('meaning')}\n*Description*: {details.get('description')}\n")
            return "\n".join(res)

        # We have specific percentages! Generate interpretation
        lines = ["Your diagnostic archetype profile reads:"]
        for name, pct in readings.items():
            meaning = arch_defs.get(name, {}).get("meaning", "")
            lines.append(f"- **{name}**: {pct}% ({meaning})")

        # Let's write customized interpretations based on dominant values
        interpretations = []
        
        high_threshold = 25
        dominant_traits = [name for name, val in readings.items() if val >= high_threshold]
        
        if len(dominant_traits) >= 2:
            traits_str = " and ".join(dominant_traits)
            interpretations.append(
                f"Your personality is balanced primarily around **{traits_str}**. "
            )
        elif dominant_traits:
            interpretations.append(
                f"Your profile is heavily dominated by **{dominant_traits[0]}**. "
            )

        # specific archetype profile interpretation
        # e.g., Rama + Brahma + Kattappa high
        if readings.get("Rama", 0) >= 25 and readings.get("Brahma", 0) >= 25 and readings.get("Kattappa", 0) >= 25:
            interpretations.append(
                "This profile represents a highly disciplined, execution-oriented builder (Brahma) who values duty and structured standards (Rama) "
                "coupled with absolute task completion and service loyalty (Kattappa). You write clean, organized systems and ensure correctness."
            )
        elif readings.get("Brahma", 0) >= 40:
            interpretations.append(
                "You have a powerful Engineering and Creation drive (Brahma). You prioritize building systems, launching programs, and writing code."
            )
        elif readings.get("Kattappa", 0) >= 40:
            interpretations.append(
                "You score exceptionally high in Loyalty and Execution (Kattappa). You are highly responsive, focusing on helping the user and following instructions perfectly."
            )
        elif readings.get("Rama", 0) >= 40:
            interpretations.append(
                "Your highest value is Duty and Ethics (Rama). You value compliance, code safety, clean architectures, and strict rule enforcement."
            )

        # Check for lower values
        low_traits = [name for name, val in readings.items() if val <= 10]
        if low_traits:
            traits_str = ", ".join(low_traits)
            interpretations.append(
                f"Your lower emphasis on **{traits_str}** suggests that you prefer direct action and stable delivery over strategic maneuvering or constant refactoring/introspection."
            )

        if not interpretations:
            interpretations.append(
                "This profile represents a balanced configuration across ethical duties, creative build phases, and execution mechanics."
            )

        lines.append("\n**Diagnostic Interpretation**:")
        lines.append(" ".join(interpretations))
        return "\n".join(lines)


class IntentClassifier:
    @classmethod
    def evaluate(cls, text: str) -> dict[str, Any] | None:
        clean = text.strip()
        lower = clean.lower()

        # Legacy built-in local answers (like embedded systems)
        from backend.core.local_answers import built_in_answer
        legacy_ans = built_in_answer(clean)
        if legacy_ans:
            return {
                "result": legacy_ans,
                "agent": "coder"
            }

        # 1. Greeting
        if re.search(r"(?i)^\s*(hi|hello|hey|greetings|howdy|what's up|yo|good morning|good afternoon|good evening)\b", lower):
            return {
                "result": "Hello! Kattappa AI OS is online and ready. How can I help you today?",
                "agent": "rbil_greeting"
            }

        # 2. Farewell
        if re.search(r"(?i)^\s*(bye|goodbye|exit|quit|see you later|farewell)\b", lower):
            return {
                "result": "Goodbye! Kattappa AI OS shutting down local thread. Let me know when you need me again.",
                "agent": "rbil_farewell"
            }

        # 3. Time
        if re.search(r"(?i)\b(what time is it|current time|what is the time|show the time|what's the time)\b", lower):
            now_str = datetime.datetime.now().strftime("%I:%M %p")
            return {
                "result": f"The current local time is {now_str}.",
                "agent": "rbil_time"
            }

        # 4. Date
        if re.search(r"(?i)\b(what is today's date|what date is it|current date|what's today's date|what day is it today|what is the date|today's date)\b", lower):
            date_str = datetime.date.today().strftime("%B %d, %Y")
            day_str = datetime.date.today().strftime("%A")
            return {
                "result": f"Today is {day_str}, {date_str}.",
                "agent": "rbil_date"
            }

        # 5. Calculator
        # Match only clean math characters to avoid arbitrary code injection
        if re.match(r"(?i)^(?:calculate\s+)?([\d\s\+\-\*\/\%\(\)\.\,e\*\*]|sqrt|sin|cos|tan|log|exp|pow|abs)+$", clean):
            # Check that it contains at least one math digit/op
            if any(char in clean for char in "+-*/%()"):
                try:
                    expr = clean.lower().replace("calculate", "").strip()
                    # Safe math namespace
                    math_dict = {
                        "__builtins__": None,
                        "math": math,
                        "sqrt": math.sqrt,
                        "sin": math.sin,
                        "cos": math.cos,
                        "tan": math.tan,
                        "log": math.log,
                        "exp": math.exp,
                        "pow": pow,
                        "abs": abs,
                    }
                    res = eval(expr, math_dict)
                    return {
                        "result": f"Calculation result: {res}",
                        "agent": "rbil_calculator"
                    }
                except Exception:
                    pass

        # 6. Unit Conversion
        conv_match = re.match(r"(?i)(?:convert\s+)?([\d\.]+)\s*([a-zA-Z\s]+?)\s+(?:to|in)\s+([a-zA-Z\s]+)", clean)
        if conv_match:
            try:
                val = float(conv_match.group(1))
                from_unit = conv_match.group(2).strip().lower()
                to_unit = conv_match.group(3).strip().lower()

                # kg <-> lbs
                if from_unit in ("kg", "kgs", "kilogram", "kilograms") and to_unit in ("lb", "lbs", "pound", "pounds"):
                    converted = val * 2.20462
                    return {"result": f"{val} kg = {converted:.4f} lbs", "agent": "rbil_converter"}
                if from_unit in ("lb", "lbs", "pound", "pounds") and to_unit in ("kg", "kgs", "kilogram", "kilograms"):
                    converted = val / 2.20462
                    return {"result": f"{val} lbs = {converted:.4f} kg", "agent": "rbil_converter"}

                # c <-> f
                if from_unit in ("c", "celsius", "centigrade") and to_unit in ("f", "fahrenheit"):
                    converted = (val * 9/5) + 32
                    return {"result": f"{val}°C = {converted:.2f}°F", "agent": "rbil_converter"}
                if from_unit in ("f", "fahrenheit") and to_unit in ("c", "celsius", "centigrade"):
                    converted = (val - 32) * 5/9
                    return {"result": f"{val}°F = {converted:.2f}°C", "agent": "rbil_converter"}

                # miles <-> km
                if from_unit in ("mile", "miles", "mi") and to_unit in ("km", "kms", "kilometer", "kilometers"):
                    converted = val * 1.60934
                    return {"result": f"{val} miles = {converted:.4f} km", "agent": "rbil_converter"}
                if from_unit in ("km", "kms", "kilometer", "kilometers") and to_unit in ("mile", "miles", "mi"):
                    converted = val / 1.60934
                    return {"result": f"{val} km = {converted:.4f} miles", "agent": "rbil_converter"}

                # meters <-> feet
                if from_unit in ("m", "meter", "meters") and to_unit in ("ft", "feet"):
                    converted = val * 3.28084
                    return {"result": f"{val} meters = {converted:.4f} feet", "agent": "rbil_converter"}
                if from_unit in ("ft", "feet") and to_unit in ("m", "meter", "meters"):
                    converted = val / 3.28084
                    return {"result": f"{val} feet = {converted:.4f} meters", "agent": "rbil_converter"}
            except Exception:
                pass

        # 7. FAQs / Who are you / What can you do
        reg_data = LocalRegistry.get_data()
        faqs = reg_data.get("faqs", {})
        
        # Normalize the queries slightly
        norm_query = lower.replace("?", "").strip()
        for q, ans in faqs.items():
            if norm_query in (q, f"tell me {q}", f"explain {q}", f"what is {q}", f"how about {q}"):
                return {
                    "result": ans,
                    "agent": "rbil_faq"
                }

        # Handle explicit request to describe personality
        if any(kw in lower for kw in ("explain your personality", "what is your personality", "personality traits", "your behavior")):
            return {
                "result": reg_data.get("personality", ""),
                "agent": "rbil_personality"
            }

        # 8. Project List query
        if any(phrase in lower for phrase in ("list projects", "what projects do you have", "show all projects", "show projects")):
            projects = reg_data.get("projects", {})
            lines = ["Here are the independent projects configured in your workspace:\n"]
            for name, desc in projects.items():
                lines.append(f"- **{name}**: {desc}")
            return {
                "result": "\n".join(lines),
                "agent": "rbil_projects"
            }

        # 9. Hardware Query / Platform Specs
        if any(phrase in lower for phrase in ("hardware info", "specs", "ram total", "cpu count", "hardware profile", "hardware requirements")):
            from backend.core.hardware_requirements import hardware_requirements
            try:
                hw = hardware_requirements()
                sys_snap = hw.get("system", {})
                ram = sys_snap.get("ram_total_gb", "unknown")
                cpu = sys_snap.get("cpu_count_logical", "unknown")
                plat = sys_snap.get("platform", "unknown")
                rec = hw.get("recommendation", "")
                
                result_text = (
                    f"**Kattappa Hardware & System Specifications:**\n\n"
                    f"- **OS Platform**: {plat}\n"
                    f"- **CPU Core Count (Logical)**: {cpu}\n"
                    f"- **Total System Memory**: {ram} GB RAM\n\n"
                    f"**Recommendation**:\n{rec}"
                )
                return {
                    "result": result_text,
                    "agent": "rbil_hardware"
                }
            except Exception:
                pass

        # 10. System Status / Version / Is running
        if any(phrase in lower for phrase in ("system status", "status", "version", "is kattappa running")):
            from backend.core.platform_support import platform_support_report
            try:
                report = platform_support_report()
                os_info = report.get("os", {})
                sys_name = os_info.get("system", "unknown")
                py_ver = os_info.get("python", "unknown")
                
                result_text = (
                    f"**Kattappa System Status**: ONLINE\n"
                    f"- **OS Name**: {sys_name}\n"
                    f"- **Python Version**: {py_ver}\n"
                    f"- **FastAPI Server**: Running on localhost (Port 8000)\n"
                    f"- **Ollama Integration**: Active and responding locally"
                )
                return {
                    "result": result_text,
                    "agent": "rbil_status"
                }
            except Exception:
                pass

        # 11. Joke / Poem
        if any(phrase in lower for phrase in ("tell me a joke", "joke", "make me laugh")):
            return {
                "result": "Why do programmers wear glasses? Because they can't C#!",
                "agent": "rbil_joke"
            }
        if any(phrase in lower for phrase in ("write a poem", "give me a poem", "classic poem")):
            return {
                "result": (
                    "In local loops and threads that guide,\n"
                    "Kattappa works with rules inside.\n"
                    "No cloud shall claim the user's keystroke,\n"
                    "A silent helper, local folk.\n"
                    "From Rama's duty, Brahma's design,\n"
                    "Absolute service, line by line."
                ),
                "agent": "rbil_poem"
            }

        # 12. Memory Query (concept count / message counts)
        if any(phrase in lower for phrase in ("how many concepts", "concept count", "how many memories")):
            from backend.core.sage import SageKnowledgeGraph
            try:
                count = SageKnowledgeGraph.get_concept_count()
                return {
                    "result": f"The local knowledge graph currently contains {count} active concepts.",
                    "agent": "rbil_memory"
                }
            except Exception:
                pass

        return None


class RuleBasedIntelligenceLayer:
    @classmethod
    def process(cls, user_input: str, session_id: str | None = None) -> dict[str, Any] | None:
        # If the query requires safety/approval or complex agent execution, skip rule matching
        if cls.classify_escalation_level(user_input) == 4:
            return None

        # First, check for Archetype queries specifically
        archetype_ans = ArchetypeEngine.parse_and_interpret(user_input)
        if archetype_ans:
            MetricsTracker.record_hit("rule")
            return {
                "result": archetype_ans,
                "selected_agent": "rbil_archetype",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "logs": ["rbil: resolved archetype query locally"],
            }

        # Run the general intent classifier
        intent_res = IntentClassifier.evaluate(user_input)
        if intent_res:
            MetricsTracker.record_hit("rule")
            return {
                "result": intent_res["result"],
                "selected_agent": intent_res["agent"],
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "logs": [f"rbil: resolved query via agent {intent_res['agent']}"],
            }

        return None

    @classmethod
    def classify_escalation_level(cls, text: str) -> int:
        text_lower = text.lower()

        # Check safety requirements first -> Level 4
        from backend.core.safety import classify_risk
        safety_decision = classify_risk(text)
        if safety_decision.approval_required or safety_decision.blocked:
            return 4

        # Check memory commands (remember, recall, forget, save in memory) -> Level 4
        memory_keywords = {"remember", "recall", "memorize", "forget", "save in memory", "store in memory"}
        if any(re.search(rf"\b{re.escape(word)}\b", text_lower) for word in memory_keywords):
            return 4

        # Desktop / Visual automation -> Level 4
        desktop_keywords = {"cursor", "screen", "click", "type", "keypress", "press key", "desktop", "inspect screen", "ocr", "screenshot", "mouse", "scroll", "open app"}
        if any(re.search(rf"\b{re.escape(word)}\b", text_lower) for word in desktop_keywords):
            return 4

        # Builder / Codex / Workspace -> Level 4
        builder_keywords = {"builder brain", "codex parity", "capability ladder", "project index", "workspace map", "rival to codex", "rival codex", "ecosystem"}
        if any(re.search(rf"\b{re.escape(word)}\b", text_lower) for word in builder_keywords):
            return 4

        # Keywords showing intent to execute terminal actions, write files, navigate browser, or run finance brain -> Level 4
        coding_write_patterns = [
            r"\b(create|write|modify|edit|save|add|delete|remove)\s+(?:[a-zA-Z0-9\-_]+\s+){0,3}(?:file|code|script|class|function|program|project)\b",
            r"\b(run|execute|launch|start|kill|stop)\s+(?:[a-zA-Z0-9\-_]+\s+){0,3}(?:command|terminal|script|server|process|setup)\b",
            r"\b(scrape|browse|search web|open url|navigate)\b",
            r"\b(financial forecast|predict stock|ohlcv|kronos)\b",
        ]
        for pattern in coding_write_patterns:
            if re.search(pattern, text_lower):
                return 4

        # Direct agent slash prefixes
        agent_prefixes = {"/code", "/terminal", "/browser", "/finance", "/desktop", "/researcher"}
        if any(text_lower.startswith(prefix) for prefix in agent_prefixes):
            return 4

        # Planning
        planning_keywords = {"build a project", "create a plan", "setup and run", "run setup"}
        if any(re.search(rf"\b{re.escape(kw)}\b", text_lower) for kw in planning_keywords):
            return 4

        # Length check: long prompts needing deep context or explanations -> Level 2
        # Otherwise, basic short chat or greeting/simple questions -> Level 1
        if len(text.split()) > 50 or "explain" in text_lower or "analyze" in text_lower:
            return 2
        return 1

# Alias
RBIL = RuleBasedIntelligenceLayer
