# ADR-20: Conversation Engine Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Communicating with users in complex domains requires managing dialogue state, resolving ambiguity, and recovering from interruptions. Treating user conversations as simple text histories leads to context loss, repetitive questioning, and failure to align on goals.

### Decision
Define a robust **Conversation Engine** that tracks explicit dialogue states, grounding contexts, clarification policies, and interruption recovery steps.

---

### Core Specifications

#### 1. Dialogue State & Grounding
- **DialogueState**: Tracks conversational context (`INIT`, `QUESTIONING`, `CLARIFYING`, `EXECUTING`, `COMPLETED`).
- **Grounding**: Maintains shared concepts verified by both user and agent. A concept is not grounded until the user acknowledges it (e.g. through confirmation checks).

#### 2. Clarification & Repair Policy
- If user input ambiguity is high (e.g. semantic match probability $\le 0.70$), the engine suspends planner execution and enters the `CLARIFYING` state, generating multiple-choice options for the user.
- **Repair**: If the user corrects a previous statement, the engine updates the belief states and initiates a TMS propagation to resolve any contradictions introduced by the correction.

#### 3. Turn Taking & Interruption Recovery
- **Interruption**: If the user interrupts while Kattappa is executing a planning cycle, the engine immediately suspends lower-priority background tasks, updates the focus stack, and routes the new user query to the executive controller.
- **Context Stitching**: When recovering from an interruption, the engine uses the goal stack and context indices to stitch the conversation thread back to the original task target.
