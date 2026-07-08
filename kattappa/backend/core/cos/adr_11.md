# ADR-11: Executive Controller Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running multiple cognitive sub-agents (Planner, Scientist, Retriever, Learning engines) concurrently without a central coordinator results in execution race conditions, resource contention (token budget exhausts), and goal deadlock. A centralized "operating system kernel scheduler" is required to arbitrate goal priority and allocate execution slices.

### Decision
Define a centralized **Executive Controller** that manages attention allocation, scheduler ticks, goal arbitration, and reflection triggers across all subsystems.

---

### Core Responsibilities

#### 1. Attention & Focus Allocation
- Manages the focus stack inside Working Memory.
- Calculates and dynamically updates attention weights based on goal priorities.

#### 2. Goal Arbitration & Resource Allocator
- Resolves conflicts when two goals compete for execution.
- Evaluates token budgets, memory constraints, and CPU usage, allocating compute slices to planners.

#### 3. Interrupts & Exceptions Handler
- Intercepts error watchdogs or direct user commands and triggers immediate cognitive context switching (reflex responses).

#### 4. Cognitive Reflection Triggers
- Measures current idle periods and schedules offline sleep/replay stages to consolidate memories and optimize embeddings.

#### 5. Conflict Resolution
- Coordinates between the Truth Maintenance System (TMS) and Planners to resolve beliefs contradictions or model predictions deviations.
