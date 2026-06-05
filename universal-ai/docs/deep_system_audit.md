# Universal AI Deep System Audit

Date: 2026-05-31

## Scope

This audit covers the owned Universal AI files after excluding generated or vendor folders such as `node_modules`, Rust `target`, Python virtual environments, caches, and build output.

Snapshot:

- Files inspected by project index: 208
- Approximate owned/source lines: 38,511
- Main live system: `backend`, `apps/desktop`, launch scripts, tests, docs
- Legacy/reference system: `ai_system` and `classic-universal-ai-system`

## Architecture

Universal AI is a local-first desktop AI system:

- Desktop shell: Tauri + React in `apps/desktop`
- Backend API: FastAPI in `backend/main.py`
- Agent graph: LangGraph in `backend/core/graph.py`
- Agents: planner, memory, safety, evaluator, coder, browser, researcher, desktop, vision, voice, file, terminal, finance, self-improver
- Memory: ChromaDB for semantic recall and SQLite for chat history, approvals, long tasks, skills, reflections, install jobs, and tool scouting
- Model runtime: Ollama through `backend/core/model_router.py`
- Tool adapters: browser, screen/OCR, desktop, terminal, file, voice, code, Finance Brain
- Safety: keyword risk classifier, approval queue, disabled shell/desktop by default

## Strengths

- Local-first design with Ollama, SQLite, ChromaDB, and local adapters.
- Approval gates exist for risky categories.
- Memory is not just vector memory; important workflows are tracked structurally in SQLite.
- The desktop UI already exposes chat history, tasks, approvals, tools, agents, and settings.
- Tests cover core backend endpoints, approval lifecycle, operator guidance, self-evolution, project indexing, and Finance Brain.
- External projects are kept in a registry instead of being silently absorbed into the core.
- The new Kronos Finance Brain keeps Kronos as a replaceable adapter and owns validation/risk language locally.

## Main Weaknesses

- There are two overlapping systems: the current `backend` system and the older `ai_system`/`classic-universal-ai-system` code. That increases maintenance load.
- The desktop React file is large and mixes API fetching, state, routing, rendering, and widgets in one file.
- Browser search currently reads a search engine HTML page directly; it is useful but brittle.
- Safety is mostly keyword-based. It catches obvious risks but does not yet reason about tool-specific arguments deeply.
- CORS was too broad before this audit. It is now restricted to local development, backend, and Tauri origins.
- Terminal allowlisting was prefix-based before this audit. It is now token-based and rejects shell control characters for safe commands.
- Tauri CSP is still permissive because changing it needs a UI regression pass in the packaged desktop app.

## Improvements Made

- Added `backend/core/hardware_requirements.py`.
- Added `GET /system/hardware-requirements`.
- Tightened FastAPI CORS from `*` to local/Tauri origins.
- Tightened terminal safe-command handling:
  - no shell metacharacters for safe commands
  - token-based matching for commands such as `git status`
  - safe commands execute without `shell=True`
- Added hardware requirements to README.
- Kept Kronos dependencies in requirements and exposed Finance Brain status/forecast APIs.

## Recommended Next Improvements

1. Split `apps/desktop/src/App.tsx` into API client, layout, chat panel, projects panel, tools panel, agents panel, tasks panel, and settings panel.
2. Add a structured tool-risk policy per adapter instead of only keyword matching.
3. Add a packaged-app CSP pass for Tauri after visual regression testing.
4. Add a proper search provider abstraction rather than scraping search HTML directly.
5. Add model-profile storage: model name, size, RAM/VRAM expectation, installed status, recommended role.
6. Add SQLite migrations with schema versioning.
7. Add telemetry-free local performance logs: response latency, model used, memory retrieval time, tool runtime.
8. Move legacy `ai_system` and `classic-universal-ai-system` behind docs/reference status or archive them once no launcher depends on them.

## Hardware Summary

Use `GET /system/hardware-requirements` for the live machine-readable version.

- Minimum: 4-core CPU, 8 GB RAM, integrated GPU, 25 GB SSD. Small model chat only.
- Recommended: 8-core CPU, 32 GB RAM, 8-12 GB VRAM, 100 GB NVMe. Comfortable daily use.
- Full potential: 12-16 core CPU, 64 GB RAM, 16-24 GB VRAM, 250 GB NVMe. Strong local models, vision, voice, Kronos.
- Maximum local lab: 24-32 core CPU, 128-256 GB RAM, 48 GB+ VRAM, 1-2 TB NVMe. Parallel models and heavy experimentation.

Even the maximum local tier is not enough to train a Kronos-scale financial foundation model from scratch; that would require a multi-GPU training cluster and large licensed market-data pipelines.
