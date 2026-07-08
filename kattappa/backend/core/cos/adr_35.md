# ADR-35: Model Registry Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Hardcoding model parameters (context lengths, provider endpoints, tokenizers, costs, tool-calling APIs) across multiple modules creates high coupling. When switching LLMs (e.g. from local Ollama to remote API), the codebase suffers from scattered edits and integration errors.

### Decision
Define a centralized **Model Registry** that manages model configurations, capabilities, tokens, and cost profiles.

---

### Core Specifications

```python
class ModelProfile:
    model_name: str
    provider: str                   # e.g., 'openai', 'anthropic', 'ollama', 'gemini'
    tokenizer_name: str
    context_length: int
    input_cost_per_million: float   # USD
    output_cost_per_million: float  # USD
    supports_multimodal: bool
    supports_tool_calling: bool
    max_concurrent_requests: int
```

```python
class ModelRegistry:
    profiles: Dict[str, ModelProfile]
    active_primary_model: str
    active_embedding_model: str
```

---

### Routing & Tokenizer Gating
- The Executive Controller queries the `ModelRegistry` to instantiate the appropriate tokenizer and enforce context truncation bounds.
- If a high-volume batch processing job (reflection replay) is initiated, the registry routes the request to a cheaper local model, conserving the premium model's token limits for interactive tasks.
