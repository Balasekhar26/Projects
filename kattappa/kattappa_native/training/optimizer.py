"""
KM-5.3 — AdamW Optimizer Configuration
========================================
Applies separate weight decay groups:
  - Decay: weight matrices (no bias, no norm params)
  - No decay: bias, LayerNorm, embeddings
"""

import torch
from typing import Iterable


def build_optimizer(
    model: torch.nn.Module,
    lr: float = 3e-4,
    weight_decay: float = 0.1,
    betas: tuple = (0.9, 0.95),
    eps: float = 1e-8,
) -> torch.optim.AdamW:
    """
    Returns a configured AdamW optimizer with decoupled weight decay groups.

    Only 2D+ parameters (weight matrices) receive weight decay.
    Biases, LayerNorm weights, and embeddings are excluded from decay.
    """
    decay_params = []
    no_decay_params = []

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        # Exclude 1-D parameters and named exceptions from decay
        if param.dim() < 2 or "norm" in name.lower() or "bias" in name.lower():
            no_decay_params.append(param)
        else:
            decay_params.append(param)

    optimizer_groups = [
        {"params": decay_params,    "weight_decay": weight_decay},
        {"params": no_decay_params, "weight_decay": 0.0},
    ]

    n_decay    = sum(p.numel() for p in decay_params)
    n_no_decay = sum(p.numel() for p in no_decay_params)
    print(f"  Optimizer groups:")
    print(f"    decay    params: {n_decay:>12,}  (weight_decay={weight_decay})")
    print(f"    no-decay params: {n_no_decay:>12,}  (weight_decay=0.0)")

    return torch.optim.AdamW(
        optimizer_groups,
        lr=lr,
        betas=betas,
        eps=eps,
        fused=True if torch.cuda.is_available() else False,
    )
