# ADR-09: Learning Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Learning in a cognitive architecture cannot rely on a single algorithm (e.g. only offline fine-tuning). Kattappa requires immediate updates from conversational feedback (online learning), automatic generalization of entities (unsupervised clustering), and policy adjustments from prediction error (reinforcement learning).

### Decision
Define a modular **Learning Framework** containing interchangeable learning strategies.

```
                      Learning Strategy Interface
       ┌───────────────────┼────────────────────┐
       ▼                   ▼                    ▼
   Online Learner      Offline Replay      Auto-Encoder
 (Episodic Updates)   (Sleep/Reflection)   (Concept Discovery)
```

---

### Learning Subsystem Specifications

| Learning Module | Training Paradigm | Subsystem Targets |
| :--- | :--- | :--- |
| **Supervised** | Fine-tuning and prompt adjustment | Tool selectors, intent classifiers. |
| **Unsupervised** | K-means, DBSCAN clustering | Latent Concept Discovery (K25). |
| **Self-supervised** | Predictive processing (Contrastive loss) | Embeddings & World dynamics transitions. |
| **Reinforcement** | Q-learning / Policy optimization | Planner path selection policies (K26.5). |
| **Online** | Dynamic memory updating | Working memory and episodic updates. |
| **Offline Replay** | Batch consolidate replay buffers | Long-term memory compression. |
| **Meta-learning** | Few-shot task adaptability tuning | Subsystem weight tuning. |

---

### Interface Contract

```python
class LearningStrategy:
    def process_experience(self, experience: ExperienceRecord) -> None:
        """Processes an episodic experience and updates the underlying model/weights."""
        pass
```
All learning modules are triggered asynchronously by the Executive Controller or during the reflection Sleep stage.
