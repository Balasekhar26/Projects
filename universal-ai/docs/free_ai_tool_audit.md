# Free AI Tool Audit

Audit date: 2026-06-05

Rule: add only tools that are free/open/local enough to improve the projects without creating a paid dependency. Freemium, credit-limited, enterprise-priced, account-locked, or unclear tools stay out of the core and get free/local replacements where useful.

## Added

- `qwebbridge`: MIT, self-hosted browser bridge. Replacement for Kimi WebBridge and safer than adopting an AI browser as a dependency.
- `gemma4_12b`: Apache-2.0 local multimodal model profile for future local reasoning, coding, image/audio understanding, and edge assistants.
- `google_ai_edge_gallery`: Apache-2.0 on-device AI sandbox for mobile/edge experiments.
- `litert_lm`: future mobile local LLM runtime candidate. License must be checked again before embedding packages directly.
- `hugging_face_papers`: free research/model discovery source.
- `benchlm`: public benchmark and price-performance reference for model selection.
- `open_source_alternative_directories`: OSSAlt/OpenAlternative/paidx-style sources for replacing paid SaaS.
- `openrouter_free_models`: cloud fallback candidate, disabled by default and limited to explicitly free models only.

## Blocked From Core

- Rocket.new: has a free one-time credit grant, but production use is credit/subscription-based.
- Gemini Canvas, NotebookLM, Perplexity AI/Comet: useful free/freemium cloud products, but proprietary and account/service dependent.
- Kimi WebBridge: local bridge idea is useful, but the project uses `qwebbridge` as the open self-hosted replacement.
- Microsoft MAI models and Frontier Tuning: Microsoft/Foundry/Copilot ecosystem, pricing or subscription dependent.
- Sensor Tower, AppKittie, EmailKowalski, Grapevine AI, ChatXP, Horizon AI, TrustMR/TrustMi/TrustML: not verified as fully free/open/local enough for core use.

## Project Fit

- Universal AI: QWebBridge, Gemma 4, AI Edge Gallery, LiteRT-LM, Hugging Face Papers, BenchLM, OSS alternative directories, OpenRouter free-model-only fallback.
- PCB Doctor: Gemma 4 and AI Edge tools for future multimodal inspection and field-device demos.
- DEWS: Gemma 4 and AI Edge tools for local/mobile field reasoning.
- Universal Translator: AI Edge Gallery/LiteRT-LM for offline mobile translation experiments.
- NeuroSeed: local Gemma/AI Edge concepts for consent-first private study assistants.
- AI Cyber Shield: QWebBridge only as approval-gated local browser automation; OSS alternative and benchmark sources for research.
