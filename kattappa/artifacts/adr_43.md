# ADR-43: API Gateway & External Interfaces Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
External software systems, web frontends, and IDE extension clients need a reliable way to query memory, dispatch goals, and trigger tasks. Exposing internal class structures directly creates integration fragility and security risks.

### Decision
Define a robust, unified **API Gateway** exposing REST, WebSocket, and gRPC endpoints with validated schemas and request authentication.

---

### Core Specifications

#### 1. Communication Protocols
- **gRPC Services**: Used for high-volume, low-latency agent-to-agent and worker cluster communication.
- **REST Endpoints**: Exposes static resource management (e.g. `/api/v1/models`, `/api/v1/configs`).
- **WebSockets**: Streams real-time events, active trace spans, and agent dialogue updates to client frontends.

#### 2. Request Security & Rate Limiting
- Clients must present an authorized JWT token.
- Enforces IP-based and token-based rate limits to prevent denial-of-service vector attacks.

#### 3. Structured Payload Validation
- All inbound requests must validate against OpenAPI/Pydantic schemas before routing to the Executive Controller parser.
