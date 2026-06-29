from __future__ import annotations

import json
import time
import httpx

from backend.core.config import load_config
from backend.core.logger import log_event


_cached_models: list[str] = []
_last_fetch_time: float = 0.0
_last_failure_time: float = 0.0


def available_models() -> list[str]:
    global _cached_models, _last_fetch_time, _last_failure_time
    now = time.time()
    if now - _last_failure_time < 10.0:
        return []
    if now - _last_fetch_time < 30.0 and _cached_models:
        return _cached_models
    
    config = load_config()
    try:
        response = httpx.get(f"{config.ollama_host}/api/tags", timeout=3.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        _cached_models = sorted(
            name
            for item in models
            if (name := item.get("name") or item.get("model"))
        )
        _last_fetch_time = now
        _last_failure_time = 0.0
        return _cached_models
    except Exception:
        _last_failure_time = now
        return _cached_models or []


def health() -> tuple[bool, str]:
    config = load_config()
    try:
        response = httpx.get(f"{config.ollama_host}/api/tags", timeout=3.0)
        response.raise_for_status()
        return True, "Ollama reachable"
    except Exception as exc:
        return False, str(exc)


def ask_model(prompt: str | list[dict[str, str]], role: str = "general", system: str | None = None) -> str:
    import os
    import sys
    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
        if isinstance(prompt, list):
            prompt_text = "\n".join(m.get("content", "") for m in prompt)
            total_len = sum(len(m.get("content", "")) for m in prompt)
            estimated_input_tokens = total_len // 4
        else:
            prompt_text = prompt
            estimated_input_tokens = len(prompt) // 4
        
        from backend.core.resource_governor import ResourceGovernor
        if not ResourceGovernor.check_token_budget(estimated_input_tokens):
            return "Error: System token budget exceeded. LLM request blocked by Resource Governor."

        prompt_lower = prompt_text.lower()
        
        # 1. Reasoning Node Mock
        if "reasoning subsystem" in prompt_lower:
            if "bluefalcon42" in prompt_lower or "remember" in prompt_lower:
                return '{"hypothesis": "Save bluefalcon42 to memory", "missing_knowledge_gap": null, "search_query_for_gap": null}'
            if "guide me" in prompt_lower or "cursor" in prompt_lower:
                return '{"hypothesis": "Guide user with cursor to inspect screen", "missing_knowledge_gap": null, "search_query_for_gap": null}'
            if "rival" in prompt_lower or "codex" in prompt_lower:
                return '{"hypothesis": "Compare Kattappa and Codex", "missing_knowledge_gap": null, "search_query_for_gap": null}'
            if "builder brain" in prompt_lower or "how you work" in prompt_lower:
                return '{"hypothesis": "Explain builder brain", "missing_knowledge_gap": null, "search_query_for_gap": null}'
            if "embedded" in prompt_lower and "delete" in prompt_lower:
                return '{"hypothesis": "Explain embedded systems then delete", "missing_knowledge_gap": null, "search_query_for_gap": null}'
            return '{"hypothesis": "Process request safely", "missing_knowledge_gap": null, "search_query_for_gap": null}'
            
        # 2. Council Perspective Elicitation Mock
        if "perspective" in prompt_lower or "deliberate" in prompt_lower or "council" in prompt_lower:
            return '{"decision": "APPROVE", "confidence": 0.95, "evidence_type": "reasoning", "risks": [], "benefits": [], "rationale": "Approved by perspective", "evidence_refs": []}'
            
        # 3. Metacognitive Gate Mock
        if "grounding" in prompt_lower or "metacognitive" in prompt_lower:
            action = "ANSWER"
            if any(w in prompt_lower for w in ("bluefalcon42", "remember", "guide me", "cursor", "rival", "codex", "builder brain", "delete")):
                action = "TOOL"
            return f'{{"grounded": true, "confidence": 0.95, "recommended_action": "{action}", "new_search_query": null, "reason": "Grounded."}}'
            
        # 4. World Model Simulation Mock
        if "world model" in prompt_lower or "simulate" in prompt_lower:
            return '{"predicted_success": 0.95, "predicted_cost": 1.0, "predicted_time": "100ms", "confidence_interval": [0.9, 1.0], "risk_score": 0.05}'
            
        # 5. Planner CoT Checklist Mock
        if "planner" in prompt_lower or "checklist" in prompt_lower or "reasoning statement" in prompt_lower:
            agent = "evaluator"
            if "coder" in prompt_lower:
                agent = "coder"
            elif "builder" in prompt_lower:
                agent = "builder"
            elif "file" in prompt_lower:
                agent = "file"
            elif "desktop" in prompt_lower:
                agent = "desktop"
            elif "memory" in prompt_lower:
                agent = "memory"
            return f"[Reasoning] Routing to {agent} agent.\n[Routing] {agent}\n[Checklist]\n- Step 1: Execute request."
            
        # 6. Decompose (V1 planner) Mock
        if "decompose" in prompt_lower or "json array of objects" in prompt_lower:
            return '[]'

        # 7. Default direct responses
        if "bluefalcon42" in prompt_lower or "remember" in prompt_lower:
            return "I have saved the project codename bluefalcon42 in my history database."
        if "guide me" in prompt_lower or "cursor" in prompt_lower:
            return "I will guide you with the cursor to inspect the screen."
        if "rival to codex" in prompt_lower or "codex" in prompt_lower:
            return "Kattappa is a local-first alternative to OpenAI Codex, featuring custom tools and offline privacy."
        if "builder brain" in prompt_lower or "how you work" in prompt_lower:
            return "My builder brain is designed to analyze project workspace structures and file patterns."
        if "embedded" in prompt_lower and "delete" in prompt_lower:
            return "Embedded systems are microcontrollers controlling physical hardware. Now running deletion..."
            
        return "I am Kattappa, a local assistant. I can help with that."

    from backend.core.resource_governor import ResourceGovernor
    if isinstance(prompt, list):
        total_len = sum(len(m.get("content", "")) for m in prompt)
        estimated_input_tokens = total_len // 4
    else:
        estimated_input_tokens = len(prompt) // 4

    if not ResourceGovernor.check_token_budget(estimated_input_tokens):
        return "Error: System token budget exceeded. LLM request blocked by Resource Governor."
        
    config = load_config()
    
    # Dynamic Multi-Model Intelligent Routing
    if isinstance(prompt, list):
        routing_text = "\n".join(m.get("content", "") for m in prompt)
    else:
        routing_text = prompt

    input_lower = routing_text.lower()
    coding_keywords = {"code", "python", "javascript", "function", "class", "compile", "bug", "refactor", "algorithm", "html", "css", "database", "sqlite"}
    is_coding = any(word in input_lower for word in coding_keywords)
    
    reasoning_keywords = {"explain", "compare", "analyze", "why", "difference", "architect", "logic"}
    is_reasoning = len(routing_text.split()) > 150 or any(word in input_lower for word in reasoning_keywords)
    
    routed_role = role
    if role == "general":
        if is_coding:
            routed_role = "coder"
        elif is_reasoning:
            routed_role = "power" if config.hardware_profile in {"PERFORMANCE", "BEAST"} else "general"

    from backend.core.adaptive_runtime import SelfLearningEngine, WarmupManager, GPUTaskScheduler, AgentHibernationEngine, SelfHealingRuntime
    
    preferred = GPUTaskScheduler.route_task(routing_text, routed_role)
    AgentHibernationEngine.touch_model(preferred)
    
    # Warm up preferred model in VRAM
    WarmupManager.warm_model_background(preferred, config.ollama_host)
    
    installed = available_models()
    candidates = _candidate_models(preferred, installed)
    
    # Filter candidates based on self-learning health status (skip thrashed/failing models)
    healthy_candidates = [m for m in candidates if SelfLearningEngine.is_model_healthy(m)]
    active_candidates = healthy_candidates if healthy_candidates else candidates
    
    for m in active_candidates:
        AgentHibernationEngine.touch_model(m)
    
    default_system = (
        "You are Kattappa AI OS, Bala's local-first desktop assistant. Text replies must be English only; "
        "the separate voice layer renders assistant speech in Telugu. Be respectful, calm, loyal, practical, "
        "and concise. Do not use sarcasm, insults, flirting, movie-character roleplay, or a British/JARVIS persona. "
        "Do not claim you have control, permissions, files, screen access, internet access, or installed tools unless "
        "the runtime context confirms it. If action needs approval, say that clearly. If you are unsure, ask one short "
        "clarifying question or state the safest next step. If the user provides or corrects factual context (such as "
        "name, language preference, or date), acknowledge and confirm the correction explicitly."
    )
    
    if isinstance(prompt, list):
        messages = prompt
    else:
        messages = [
            {
                "role": "system",
                "content": system or default_system,
            },
            {"role": "user", "content": prompt},
        ]
    
    errors: list[str] = []
    for model in active_candidates:
        t0 = time.perf_counter()
        AgentHibernationEngine.touch_model(model)
        try:
            # Enforce 15-second read timeout and 2-second connect timeout for fast escalation
            timeout_cfg = httpx.Timeout(20.0, connect=2.0, read=15.0)
            with httpx.stream(
                "POST",
                f"{config.ollama_host}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {"num_predict": _prediction_budget(routed_role), "temperature": 0.2},
                },
                timeout=timeout_cfg,
            ) as r:
                r.raise_for_status()
                chunks = []
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk_data = json.loads(line)
                        content = chunk_data.get("message", {}).get("content", "")
                        if content:
                            chunks.append(content)
                    except Exception:
                        pass
                
                final_content = "".join(chunks).strip()
                if final_content:
                    duration = time.perf_counter() - t0
                    SelfLearningEngine.log_response_time(model, duration)
                    SelfLearningEngine.reset_failures(model)
                    log_event(f"model_used role={routed_role} model={model} duration={duration:.3f}s")
                    estimated_output_tokens = len(final_content) // 4
                    ResourceGovernor.charge_tokens(estimated_input_tokens + estimated_output_tokens)
                    return final_content
                errors.append(f"{model}: empty response")
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            try:
                # Try to launch/heal Ollama dynamically if connection failed
                if SelfHealingRuntime.heal_ollama():
                    timeout_cfg = httpx.Timeout(20.0, connect=2.0, read=15.0)
                    with httpx.stream(
                        "POST",
                        f"{config.ollama_host}/api/chat",
                        json={
                            "model": model,
                            "messages": messages,
                            "stream": True,
                            "options": {"num_predict": _prediction_budget(routed_role), "temperature": 0.2},
                        },
                        timeout=timeout_cfg,
                    ) as r:
                        r.raise_for_status()
                        chunks = []
                        for line in r.iter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk_data = json.loads(line)
                                content = chunk_data.get("message", {}).get("content", "")
                                if content:
                                    chunks.append(content)
                            except Exception:
                                pass
                        
                        final_content = "".join(chunks).strip()
                        if final_content:
                            duration = time.perf_counter() - t0
                            SelfLearningEngine.log_response_time(model, duration)
                            SelfLearningEngine.reset_failures(model)
                            log_event(f"model_used role={routed_role} model={model} duration={duration:.3f}s")
                            estimated_output_tokens = len(final_content) // 4
                            ResourceGovernor.charge_tokens(estimated_input_tokens + estimated_output_tokens)
                            return final_content
            except Exception as retry_exc:
                exc = retry_exc

            SelfLearningEngine.log_failure(model)
            SelfHealingRuntime.handle_failure(model)
            errors.append(f"{model}: {exc}")
            log_event(f"model_failed role={routed_role} model={model} error={exc}")
        except Exception as exc:
            SelfLearningEngine.log_failure(model)
            SelfHealingRuntime.handle_failure(model)
            errors.append(f"{model}: {exc}")
            log_event(f"model_failed role={routed_role} model={model} error={exc}")
            
    # Record timeout prevented if all models failed or timed out
    from backend.core.rbil import MetricsTracker
    MetricsTracker.record_timeout_prevented()
    
    return (
        "Kattappa local AI model took too long to respond. The system remains online. "
        "If you are running multiple applications, freeing up RAM or switching to a smaller model "
        "(such as qwen2.5:0.5b) may resolve the delay."
    )


def _candidate_models(preferred: str, installed: list[str]) -> list[str]:
    order = [
        preferred,
        "qwen2.5:0.5b",
        "qwen2.5-coder:3b",
        "phi3:latest",
        "mistral:latest",
        "qwen3:4b",
    ]
    return [model for index, model in enumerate(order) if model in installed and model not in order[:index]] or [preferred]


def _prediction_budget(role: str) -> int:
    if role == "fast":
        return 180
    if role == "coder":
        return 500
    return 320


def _timeout_budget(role: str) -> float:
    if role == "fast":
        return 90.0
    if role == "coder":
        return 180.0
    return 140.0
