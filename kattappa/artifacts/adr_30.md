# ADR-30: Safety & Alignment Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running fully autonomous tools, planners, and LLMs exposes the host system to jailbreak exploits, unauthorized write access, prompt injections, and data privacy leaks. Safety checks must be gated at the lower kernel layer of the Cognitive OS rather than relying on LLM behavior.

### Decision
Define a centralized **Safety & Alignment** architecture enforcing structural policies, input sanitization, sandbox isolation, and cryptographic auditing.

---

### Core Specifications

#### 1. Input Sanitization & Injection Defense
- Every sensory percept (user input, file read, external payload) must pass through a regex and vector-similarity injection gate.
- Matches queries against a database of known jailbreak embeddings. High similarity triggers an immediate safety exception, blocking parser routing.

#### 2. Tool Sandboxing & Permission Policies
- High-risk tool calls (filesystem writes, shell commands, database migrations) are executed inside ephemeral docker or isolated process sandboxes.
- **Human Approval Checkpoint**: Any action attempting destructive commands or outbound internet requests to unregistered domains halts execution and triggers a modal approval request to the user.

#### 3. Privacy & Secret Gating
- Filters outgoing payloads to external API engines, masking credentials, local paths, or tokens.
- Restricts memory read permissions to `RESTRICTED` memory directories unless the agent possesses an authorized signature token.
