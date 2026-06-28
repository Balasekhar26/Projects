# ADR-46: Development Workflow & Coding Standards Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
As multiple developers (and autonomous coding agents) contribute code to Kattappa, lack of uniform development workflows, coding standards, packaging rules, and naming conventions leads to code churn, merge conflicts, and dependency sprawl.

### Decision
Establish strict coding standards, interface guidelines, and package organization rules enforced through linting tools and CI pipeline configurations.

---

### Core Specifications

#### 1. Coding Standards & Naming Conventions
- **Language**: Python 3.10+ with strict type hinting.
- **Naming Style**:
  - Class/Interface names: `PascalCase` (e.g. `MemoryObject`).
  - Function/Variable names: `snake_case` (e.g. `generate_plan`).
  - Constant names: `UPPER_SNAKE_CASE` (e.g. `MAX_TICK_DURATION`).
- **Comments**: Keep docstrings on all public methods. Preserve existing comments.

#### 2. Package Organization Rules
- Directory layout:
  - `core/cos/`: Core Cognitive OS files (Executive Loop, Memory containers).
  - `core/cos/planners/`: Planning engine strategies.
  - `core/cos/reasoners/`: Reasoning registry modules.
  - `core/cos/learning/`: Continual adaptation layers.
- **Circular Dependencies**: Prohibited. Submodules must import only base interfaces or containers, never concrete engines.

#### 3. Serialization Standards
- Data exchanged across process boundaries or WebSocket streams must use Pydantic validation structures and serialize to JSON.
