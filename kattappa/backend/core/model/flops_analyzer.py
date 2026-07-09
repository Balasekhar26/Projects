"""FLOP and Compute Complexity Analyzer (Program 27C).

Estimates parameters, memory consumption (weights, optimizer, activations),
and training compute FLOPs for Kattappa transformer configuration presets.
"""
from __future__ import annotations

from typing import Any, Dict

from backend.core.model.config import KattappaConfig


class FlopsAnalyzer:
    """Estimates parameter counts, FLOPs, and VRAM requirements for model configs."""

    @classmethod
    def analyze(
        cls,
        config: KattappaConfig,
        batch_size: int = 4,
        seq_len: int = 2048,
        bytes_per_param: int = 2,  # default float16/bfloat16 (2 bytes)
    ) -> Dict[str, Any]:
        """Calculates structural, memory, and training statistics for a model configuration.

        Args:
            config:          The model architecture parameters.
            batch_size:      Batch size per GPU.
            seq_len:         Sequence length (context window).
            bytes_per_param: Precision bytes (e.g. 4 for fp32, 2 for fp16/bf16).

        Returns:
            Dict containing detailed parameter breakout, VRAM usage estimates,
            forward/backward FLOPs, and training duration bounds.
        """
        vocab = config.vocab_size
        h = config.hidden_size
        heads = config.num_attention_heads
        kv_heads = config.num_key_value_heads or heads
        head_dim = h // heads
        inter_size = config.intermediate_size or int(2 * h * 4 / 3)
        layers = config.num_hidden_layers

        # ── Parameter Breakdown ───────────────────────────────────────────────
        embedding_params = vocab * h

        # Attention params per layer
        q_proj = h * (heads * head_dim)
        k_proj = h * (kv_heads * head_dim)
        v_proj = h * (kv_heads * head_dim)
        o_proj = (heads * head_dim) * h
        attn_params_per_layer = q_proj + k_proj + v_proj + o_proj

        # MLP params per layer (SwiGLU w1, w2, w3)
        mlp_params_per_layer = 3 * h * inter_size

        # Normalization weights per layer (norm1 + norm2)
        norm_params_per_layer = 2 * h

        # Aggregate per-layer
        params_per_layer = attn_params_per_layer + mlp_params_per_layer + norm_params_per_layer
        total_layers_params = params_per_layer * layers

        # Output projection head (untied)
        lm_head_params = h * vocab

        total_norm_params = (layers * 2 + 1) * h  # norm1, norm2 per layer + final norm

        total_parameters = embedding_params + total_layers_params + total_norm_params + lm_head_params

        # ── Memory Estimations (VRAM) ─────────────────────────────────────────
        # 1. Weights memory
        vram_weights = total_parameters * bytes_per_param

        # 2. Gradients memory (usually same precision or fp32)
        vram_gradients = total_parameters * bytes_per_param

        # 3. Optimizer states (AdamW uses 8 bytes per parameter: fp32 first + second moment)
        vram_optimizer = total_parameters * 8

        # 4. Activation memory (heuristic for pre-activation storage during backward pass)
        # Activation memory scale per token: ~34 * hidden_size * num_layers + attention activation overhead
        activation_factor = 34 * h * layers + (10 * heads * seq_len * layers)
        vram_activations = batch_size * seq_len * activation_factor

        total_vram_training = vram_weights + vram_gradients + vram_optimizer + vram_activations

        # ── FLOP Calculations ─────────────────────────────────────────────────
        # Forward pass FLOPs per token (approx 2FLOPs per multiply-accumulate)
        # Core matrix multiplies: 2 * total_parameters
        # Attention scores matrix multiplies: 4 * layers * heads * seq_len * head_dim
        attn_flops_per_token = 4 * layers * heads * seq_len * head_dim
        forward_flops_per_token = (2 * total_parameters) + attn_flops_per_token

        # Backward pass FLOPs is roughly double the forward pass
        backward_flops_per_token = 2 * forward_flops_per_token
        total_flops_per_token = forward_flops_per_token + backward_flops_per_token

        return {
            "parameters": {
                "total": total_parameters,
                "embeddings": embedding_params,
                "attention_per_layer": attn_params_per_layer,
                "mlp_per_layer": mlp_params_per_layer,
                "layer_total": params_per_layer,
                "total_layers": total_layers_params,
                "lm_head": lm_head_params,
            },
            "vram_mb": {
                "weights": round(vram_weights / (1024 * 1024), 2),
                "gradients": round(vram_gradients / (1024 * 1024), 2),
                "optimizer": round(vram_optimizer / (1024 * 1024), 2),
                "activations": round(vram_activations / (1024 * 1024), 2),
                "total_training": round(total_vram_training / (1024 * 1024), 2),
            },
            "flops": {
                "forward_per_token": forward_flops_per_token,
                "backward_per_token": backward_flops_per_token,
                "total_per_token": total_flops_per_token,
            },
        }
