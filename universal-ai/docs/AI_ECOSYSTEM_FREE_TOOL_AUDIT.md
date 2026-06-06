# AI Ecosystem Free Tool Audit

This audit maps the 34 discussed AI ecosystem topics into the seven-project plan.

Rule: only fully free, open, local-first, or Kattappa-built capabilities can be added to core project plans. Paid, freemium, quota-limited, cloud-metered, closed, or unknown-license tools stay blocked until a license/source review proves they are safe enough.

## Added Free Capabilities

| Capability | Why it helps | Projects |
| --- | --- | --- |
| `deepseek_r1_local` | Local reasoning/coding model profile for Second Brain and GOAT-style planning without paid API routing. | Kattappa AI OS, NeuroSeed |
| `chromadb` | Local vector memory for private Second Brain, RAG, and study recall. | Kattappa AI OS, NeuroSeed |
| `local_eval_harness` | Local retrieval, generation, end-to-end, and production evaluation. | All seven projects |
| `ragas_or_deepeval_local` | Optional open-source RAG quality checks, kept as replaceable adapters. | Kattappa AI OS, PCB Doctor |
| `mermaid` | Free diagram-as-code replacement for Napkin/Graphify-style diagrams. | Kattappa AI OS, PCB Doctor, Cyber Shield, Musical Keyboard, DEWS, NeuroSeed |
| `excalidraw` | Free/open sketch-board replacement for visual thinking and learning maps. | Kattappa AI OS, PCB Doctor, NeuroSeed |
| `argos_translate` | Offline translation without Sarvam/BHASHINI cloud dependency. | Universal Translator |
| `vosk` | Offline STT for weak machines. | Universal Translator |
| `faster_whisper` | Local STT for voice commands and translation. | Universal Translator, Kattappa voice stack |
| `piper_tts` | Local TTS replacement for paid/cloud voice APIs. | Universal Translator, Kattappa voice stack |
| `openwakeword` | Offline wake-word engine for Kattappa, Mama, and Kittu. | Universal Translator, Kattappa AI OS |
| `opencode_local_coding_loop` | Free local Claude Code/BLACKBOX/Merlin-style coding workflow. | Kattappa AI OS |
| `qiskit` | Free quantum SDK for Kaveri/QpiAI-inspired learning labs. | Kattappa AI OS, Cyber Shield, NeuroSeed |
| `local_b2b_playbook` | Local product workflow templates for B2B and AI-worker planning. | Kattappa AI OS |
| `local_sovereign_frugal_ai_patterns` | Local-first architecture rules for sovereign/frugal/evidence-tested AI. | Kattappa AI OS, Cyber Shield, DEWS, NeuroSeed |

## Blocked Or Replaced

| Topic | Decision | Free replacement |
| --- | --- | --- |
| Terafab / TeraFab | Research inspiration only until a free/open local tool is verified. | `open_source_alternative_directories`, `local_b2b_playbook` |
| BLACKBOX AI | Blocked from core because it is not a fully local/open dependency. | `opencode_local_coding_loop`, `deepseek_r1_local`, `gemma` |
| Graphify / Grafyfy | Block unless the exact tool license is verified. | `mermaid`, `excalidraw`, `networkx` |
| Claude AI / Claude Code / EEC patterns | Block paid/cloud dependency; learn workflow patterns only. | `opencode_local_coding_loop`, `deepseek_r1_local`, `local_repo_prompt_exporter` |
| Scale AI | Block as a paid/commercial platform dependency. | `local_eval_harness`, `ragas_or_deepeval_local` |
| Sarvam AI / Shuka / Bulbul | Keep paid speech/translation out of core; free LLM references are research-only. | `faster_whisper`, `vosk`, `argos_translate`, `piper_tts` |
| BHASHINI | Research-only unless a safe free public use path is verified. | `argos_translate`, `faster_whisper`, `vosk`, `piper_tts` |
| BharatGPT | Unknown/closed status for core project use. | `gemma`, `deepseek_r1_local` |
| Mythos | Unknown/closed until source/license review. | `mirofish`, `local_sovereign_frugal_ai_patterns` |
| Merlin AI | Blocked as external commercial coding workspace. | `opencode_local_coding_loop`, `chromadb`, `local_repo_prompt_exporter` |
| Napkin AI | Freemium/cloud visual tool, not core. | `mermaid`, `excalidraw` |
| xAI / Grok | Freemium/cloud/API metering, not core. | `deepseek_r1_local`, `gemma` |
| DeepSeek API | Cloud API blocked from core; local open-weight model allowed. | `deepseek_r1_local` |
| Kaveri / QpiAI | Use only as learning inspiration until free/open details are verified. | `qiskit` |
| Odysseus repo | Do not copy until license is inspected. | `local_repo_prompt_exporter`, `opencode_local_coding_loop` |
| CLI Anything | Pattern added, not a new external dependency. | one setup file and one run file per project |

## Concept Mappings

- Subquadratic / SubQ: use as an efficiency target in retrieval, memory, and long-context indexing.
- Retrieval Evaluation: added to `local_eval_harness`.
- Generation Evaluation: added to `local_eval_harness`.
- End-to-End Evaluation: added to `local_eval_harness`.
- Production Evaluation: added to `local_eval_harness`.
- Frugal AI: added to `local_sovereign_frugal_ai_patterns`.
- Sovereign AI: added to `local_sovereign_frugal_ai_patterns`.
- Combat-Proven AI: translated into stress tests, incident drills, and failure logs.
- AI Employees Are Here: mapped to approval-gated specialist workers.
- Voice AI Explosion: mapped to offline wake word, STT, VAD, TTS, and latency checks.
- The B2B Master Stroke: mapped to `local_b2b_playbook`.
- Second Brain + DeepSeek API + GOAT system: mapped to `chromadb`, SQLite memory, local embeddings, and `deepseek_r1_local`.

## Hard Boundary

No paid API, trial credit, hidden cloud routing, unknown-license repository, or source-blind code copy is added to the seven-project core. Any future external install must still pass source/license inspection and user approval.
