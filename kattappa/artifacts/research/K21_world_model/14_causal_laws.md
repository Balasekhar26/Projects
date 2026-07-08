# K21-14: Causal Laws Registry

This document specifies the structure and schema rules for registering and executing Causal Laws.

---

## 1. Causal Law Schema

Causal Laws represent reusable transition functions that are independent of specific entity instances. Every registered law conforms to the following schema:

```python
@dataclass
class CausalLaw:
    law_id: str             # Unique identifier (e.g. 'law_compilation_cpu_spike')
    description: str
    inputs: List[str]       # Types or concepts required (e.g. ['DigitalEntity', 'SelfEntity'])
    conditions: str         # Pre-condition logic constraints
    outputs: List[str]      # Properties updated
    confidence: float       # Rule reliability factor (0.0 to 1.0)
    domain: str             # Domain code (Physical, Digital, etc.)
    version: str            # Version string (e.g. '1.0.0')
    priority: int           # Execution priority tree (lower is executed first)
```

---

## 2. Cross-Domain Causal Engine

Causality is evaluated separately from the database layer by the **Causal Engine**:

```
[Digital Event: file_compiled]
       │
       ▼
 [EventBus] ──> [Causal Engine] ──> [Matches CausalLaw: compile_heat]
                                              │
                                              ▼
                                 [Self Event: cpu_spike]
                                              │
                                              ▼
                                   [Self Domain update]
```

- When an event is published, the `CausalEngine` retrieves all matching `CausalLaw` records, evaluates conditions, and publishes secondary events (e.g. `SelfEvent`) to propagate states across domains.
