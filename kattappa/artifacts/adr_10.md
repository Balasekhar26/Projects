# ADR-10: Safety & Governance Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
As autonomous planners, scientists, and learning loops run continuously, the risk of agent drift, data contamination, infinite execution loops, or unauthorized tool executions increases exponentially. Safety constraints cannot be patched as high-level prompts; they must be gated at the core OS layer.

### Decision
Implement strict safety boundaries and governance policies enforced at the kernel boundary of the Cognitive OS.

---

### Core Governance Constraints

#### 1. Access Control & Memory Permissions
- Memory objects are classified into `privacy_level` ranges (`PUBLIC`, `PRIVATE`, `RESTRICTED`).
- Sub-agents or external tools must verify authorization credentials before querying RESTRICTED semantic directories.

#### 2. Executable Tool Permissions & Sandboxes
- High-risk tools (e.g. filesystem write, command execution, database drops) require a signed authorization ticket.
- Any command execution that modifies workspace files or database schema must trigger a **Human Approval Checkpoint**, halting loop execution until explicitly approved.

#### 3. Hallucination Detection & Verification Gates
- **Confidence Thresholds**: Inference results with combined probability under `min_probability=0.50` cannot be acted upon or saved as a semantic belief.
- **Rollback Policies**: If a reasoning contradiction cannot be resolved by the TMS, or if the prediction error on a plan exceeds predefined thresholds, the current coordinator branch is rolled back.
- **Audit Logs**: Every transition, action, and learning adjustment writes a cryptographic hash to an immutable local audit trail.
- **Resource watchdogs**: Memory usage, CPU load, and total API tokens have absolute limits per cognitive cycle tick.
