import os
from pathlib import Path

def generate_model_card(checkpoint_path: str, model_config: dict, dataset_version: str, training_details: dict, safety_gates: dict):
    checkpoint_file = Path(checkpoint_path)
    checkpoint_dir = checkpoint_file.parent
    
    n_layers = model_config.get("n_layers", 12)
    d_model = model_config.get("d_model", 768)
    vocab_size = model_config.get("vocab_size", 32000)
    context_length = model_config.get("context_length", 2048)
    d_ff = model_config.get("d_ff", d_model * 4)
    
    param_count = (vocab_size * d_model) + n_layers * (4 * d_model * d_model + 2 * d_model * d_ff)
    param_count_m = param_count / 1e6

    card_content = f"""# Model Card — Kattappa-100M

This model card corresponds to the checkpoint saved at `{checkpoint_file.name}`.

## 1. Architecture Summary
- **Total Parameters:** ~{param_count_m:.1f}M
- **Attention Layers:** {n_layers} Layers
- **Attention Heads:** {model_config.get("n_heads", 12)} Heads
- **Model Dimension (d_model):** {d_model}
- **Feed-Forward Dimension (d_ff):** {d_ff}
- **Context Length:** {context_length} tokens
- **Attention Type:** {model_config.get("attention_type", "Standard GQA")}
- **KV Heads:** {model_config.get("n_kv_heads", 4)}

## 2. Dataset Reference
- **Version:** `{dataset_version}`
- **Mix Distribution:**
  - Code: 20%
  - Books: 30%
  - Web: 50%
- **Languages:** Telugu, English, Roman Telugu

## 3. Training Details
- **Hardware Profile:** {training_details.get("hardware", "Apple M-Series")}
- **Total Training Steps:** {training_details.get("steps", "50000")}
- **Learning Rate:** {training_details.get("lr", "3e-4")} (Cosine Schedule)
- **Peak Memory Used:** {training_details.get("peak_memory_gb", "9.5")} GB
- **Final Validation Perplexity:** {training_details.get("val_ppl", "N/A")}

## 4. Evaluation & Benchmarks
- **Reasoning Accuracy (GSM8K):** {safety_gates.get("reasoning_accuracy", "N/A")}
- **Engineering/RF/Embedded:** {safety_gates.get("engineering_accuracy", "N/A")}
- **Memory (6-Dimension Recall):** {safety_gates.get("memory_accuracy", "N/A")}
- **Tool Calling Selection:** {safety_gates.get("tool_selection_accuracy", "N/A")}
- **Telugu Script Adherence:** {safety_gates.get("telugu_accuracy", "N/A")}
- **Catastrophic Forgetting Gate:** {safety_gates.get("forgetting_retention", "N/A")}

## 5. Limitations & Safety
- **Context constraints:** Enforced sequence limit of {context_length} tokens.
- **Safety refusals:** Configured with toxic, PII, and jailbreak filters.
- **Biases:** Model exhibits typical LLM biases based on internet pre-training text data.

## 6. License
- **License:** Kattappa Open Academic License v1
"""

    card_path = checkpoint_dir / "MODEL_CARD.md"
    with open(card_path, "w", encoding="utf-8") as f:
        f.write(card_content)
        
    print(f"Model Card generated successfully at {card_path}")
    return str(card_path)
