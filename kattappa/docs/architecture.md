# Kattappa AI OS Architecture

Kattappa AI OS is a local-first desktop AI operating layer.

Motive:

Kattappa AI OS is Bala's personal and professional assistant for the installed system. It should take user input from the chat box or voice wake names, let one manager worker route the task, assign specialist workers for each task type, use only fully free/local-first tools as core dependencies, and continuously improve itself through an approval-gated improvement worker. When a new task needs a capability, it searches for the best fully free/open-source tools or technologies, including external tools that can run locally or in the cloud, learns the pattern, and either rebuilds the behavior locally or wraps the tool as a replaceable adapter after source/license and data-flow inspection.

- Desktop: Tauri + React
- Backend: FastAPI + WebSockets
- Brain: LangGraph
- Models: Ollama router
- Memory: ChromaDB vector memory + SQLite structured memory
- Tools: Playwright, PyAutoGUI, PowerShell, file tools, screen OCR, voice tools
- Coding: local coder model, Git, tests, isolated Aider/OpenHands setup
- Safety: approval gates, logs, rollback protocol

Runtime flow:

```text
Desktop/WebSocket -> FastAPI -> Executive Controller (Perceive -> Retrieve -> Reason -> Plan -> Act -> Learn) -> Safety -> Specialist Worker -> Evaluator -> Memory
```

Executive Controller & Cognitive OS:

- **Loop & Scheduling Ticks**: Enforces a regular scheduler tick rate (100ms) on a background thread loop.
- **Tick Lifecycle**: Executes sequential cognitive stages: `Perceive -> Retrieve -> Reason -> Plan -> Act -> Learn` during nominal ticks.
- **Interrupt Semantics**: Instantly halts normal stage execution upon receipt of a high-priority interrupt (e.g. `USER_INTERVENTION`, `SAFETY_VIOLATION`, `OUT_OF_MEMORY`), switching focus context to handle the interrupt immediately.
- **Resource Budgeting**: Maps task complexity to token and compute latency limits, timing out operations that overrun their allocations to trigger clean recovery paths.

Worker model:

- Manager worker: reads the chat request, detects risk, selects the right specialist worker, and keeps approval gates visible.
- Specialist workers: coding, browser, desktop, file, terminal, vision, voice, research, finance, memory, safety, builder, and evaluator workers.
- Improvement worker: watches results/reflections and proposes safer, better local tools or skills.
- Tool scout worker: searches for fully free/open-source technologies, blocks paid/freemium core dependencies, and converts good ideas into build-own or adapter proposals.

Multi-system cluster mode:

- Status: planned, not enabled by default.
- Rule: Kattappa AI OS may auto-connect only after every machine is explicitly paired by its owner/admin. No hidden install, silent join, covert monitoring, or unknown-user operation.
- Manager node: keeps the primary chat, approvals, memory source of truth, project map, and safety policy.
- Worker nodes: run only approved delegated jobs that fit their hardware and permissions.
- Auto-connect lifecycle: after pairing, the manager may automatically connect to one or more paired workers when local capability is insufficient, start or wake worker processes, run normal non-sensitive jobs such as inference/indexing/tests/simulation, return results to the manager, then disconnect or idle workers.
- Capability routing: each node reports CPU, RAM, OS, and later GPU/VRAM. The manager runs work locally when it fits the local profile and delegates heavier work to approved nodes when needed. Weak nodes run only light tasks; strong nodes can take heavier tasks but are never unlimited, and workers must reject assignments beyond measured hardware or permission limits.
- Approval scope: the installation agreement covers ordinary non-sensitive cluster participation and task routing after device pairing. Runtime approval is still required for shell commands, installs/downloads, file writes, desktop control, credentials, destructive actions, or sensitive data transfer.
- Storage routing: the task-origin manager node is the source of truth for chat history, task history, approvals, and long-term memory. The only durable cross-system shared data is approved, sanitized improvement data. Worker nodes receive temporary task context, return results, and delete task context after completion, failure, or cancellation instead of storing user chat/task history.
- Shared workspace: paired systems can use the Git-backed shared improvement registry for approved sanitized improvement proposals. Task workspace context sent to workers is temporary and must be deleted after the assigned work. Shared workspace does not mean shared private data; raw chats, private task context, task payloads, approval notes, secrets, sensitive local files, and machine-private memory stay out of durable shared storage.
- Improvement sync: approved self-improvement proposals stay in Kattappa's local `docs/IMPROVEMENT_REGISTRY.md` by default. Nothing is pulled from or pushed to sibling project folders. Git publication happens only when the user explicitly requests it, and new improvement data still stays pending until local approval.
- Free tools: Ray is the first worker-orchestration adapter; exo is the later local multi-machine inference adapter.
- Security: trusted LAN or user-controlled VPN only; remote shell, desktop, file writes, installs, and destructive actions require approval.
