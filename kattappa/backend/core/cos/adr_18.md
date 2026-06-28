# ADR-18: Attention Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
FRONTIER cognitive architectures process massive amounts of incoming sensory data and long-term memory records. Processing all information uniformly creates a bottleneck, slow planning latencies, and high token consumption. The system needs a way to filter, select, and sustain focus on the most relevant information.

### Decision
Define a unified **Attention Architecture** that calculates dynamic attention values for every active memory node, prioritizing working memory and scheduling execution.

---

### Attention Formula & Dynamics

The attention score of node $i$ is calculated using a multi-factor combination:
$$\text{AttentionScore}(i) = \alpha \cdot \text{Saliency} + \beta \cdot \text{Novelty} + \gamma \cdot \text{Recency} + \delta \cdot \text{Surprise} + \epsilon \cdot \text{Importance}$$

Where:
- **Saliency**: Relevancy to the active goal stack.
- **Novelty**: Recency of the node entering working memory.
- **Recency**: Time decay based on access timestamps: $e^{-\lambda (t - t_{last})}$.
- **Surprise**: The absolute prediction error between predicted state $P(s' \mid s, a)$ and observed state:
  $$\text{Surprise} = \|\text{PredictionError}\|$$
  High surprise triggers an immediate interrupt, shifting attention to the unexpected node.
- **Importance**: The static base-level utility weight.

---

### Attention Control Modes
1. **Executive Attention**: Focused, goal-directed computation slot. Only nodes with attention scores above `0.75` are admitted to the active executive reasoning cycle.
2. **Sustained Attention**: Keeping key nodes active across multiple ticks by applying a temporary attention boost while a goal is executing.
3. **Decay & Focus Competition**: In every cognitive cycle tick, attention values decay by a factor $d$. If the focus stack exceeds capacity, low-attention nodes are evicted.
4. **Interrupt Handling**: When a sensor detects a safety alert or high-surprise error event, it generates a high-priority interrupt, instantly clearing the focus stack and placing the alert node at the top.
