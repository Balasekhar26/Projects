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


def ask_model(prompt: str, role: str = "general", system: str | None = None) -> str:
    config = load_config()
    
    # Dynamic Multi-Model Intelligent Routing
    input_lower = prompt.lower()
    coding_keywords = {"code", "python", "javascript", "function", "class", "compile", "bug", "refactor", "algorithm", "html", "css", "database", "sqlite"}
    is_coding = any(word in input_lower for word in coding_keywords)
    
    reasoning_keywords = {"explain", "compare", "analyze", "why", "difference", "architect", "logic"}
    is_reasoning = len(prompt.split()) > 150 or any(word in input_lower for word in reasoning_keywords)
    
    routed_role = role
    if role == "general":
        if is_coding:
            routed_role = "coder"
        elif is_reasoning:
            routed_role = "power" if config.hardware_profile in {"PERFORMANCE", "BEAST"} else "general"

    from backend.core.adaptive_runtime import SelfLearningEngine, WarmupManager, GPUTaskScheduler, AgentHibernationEngine, SelfHealingRuntime
    
    preferred = GPUTaskScheduler.route_task(prompt, routed_role)
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
        "clarifying question or state the safest next step."
    )
    
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
            # Enforce 3-second read timeout and 2-second connect timeout for fast escalation
            timeout_cfg = httpx.Timeout(10.0, connect=2.0, read=3.0)
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
                    return final_content
                errors.append(f"{model}: empty response")
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            try:
                # Try to launch/heal Ollama dynamically if connection failed
                if SelfHealingRuntime.heal_ollama():
                    timeout_cfg = httpx.Timeout(10.0, connect=2.0, read=3.0)
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
