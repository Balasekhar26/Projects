# ADR-39: Observability & Telemetry Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Debugging non-deterministic cognitive cycles is difficult. If an agent fails to retrieve a key memory, or if the planner chooses a suboptimal subtask path, tracing the root cause without granular execution span logs is nearly impossible.

### Decision
Implement a structured **Observability & Telemetry** system mapping logs, trace spans, and performance metrics across the entire cognitive loop.

---

### Core Specifications

#### 1. Cognitive Trace Spans
- Every tick cycle generates a unique `CycleTraceID`.
- Sub-spans are generated for each active stage:
  - `perception.decode`
  - `memory.retrieve`
  - `reasoning.tms`
  - `planner.search`
  - `action.execute`

#### 2. Key Performance Metrics
- **Context Hit Ratio**: Vector and graph similarity search yields.
- **TMS Contradiction Rate**: Number of logical conflicts resolved per tick.
- **Latency Spans**: Execution duration per reasoning block.
- **Token Efficiency**: Consumed tokens per planning step.

#### 3. Log Exporters
- Exports spans using open telemetry standards (e.g. Jaeger or OpenTelemetry collectors).
- Supports local JSON console logging for developer debugging.
