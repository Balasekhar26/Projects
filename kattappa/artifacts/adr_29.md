# ADR-29: Learning Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Cognitive updates must occur across multiple timescales. Online learning updates working context immediately, while offline consolidation aggregates logs into semantic properties. Lacking a structured learning engine with defined training pathways leads to memory drift and loss of acquired skills.

### Decision
Define a multi-timescale **Learning Architecture** that coordinates online adaptation, reinforcement learning from prediction errors, and offline consolidation.

---

### Core Specifications

#### 1. Online Learning (Short-Timescale)
- Instantly updates attention values, working memory stacks, and active belief probabilities based on user feedback or action validation outputs.

#### 2. Reinforcement & Preference Learning
- **Prediction Error Update**: Planners optimize path selection policies by minimizing prediction error ($result - prediction$).
- **Preference Learning**: Learns user intent alignments through interactive corrections, writing preference constraints directly to the self model.

#### 3. Continual Adaptation (Forgetting & Replay)
- Integrates memory replay buffers to reinforce rarely accessed but critical skills (e.g. disaster recovery commands), avoiding catastrophic forgetting during offline sleep cycles.
