"""
KM-5.2 — SwiGLU Feed-Forward Block
=====================================
Implements the SwiGLU gated feed-forward network used in each
Kattappa-100M decoder block.

SwiGLU formula:
    FFN(x) = (SiLU(xW_gate) ⊙ xW_up) @ W_down

This is the same activation used in LLaMA, Mistral, and Qwen.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class SwiGLUMLP(nn.Module):
    """
    SwiGLU Feed-Forward Network.

    Args:
        d_model: Input/output dimension (768 for Kattappa-100M).
        d_ff:    Inner hidden dimension (3072 = 4 × d_model by default).
        dropout: Dropout rate.
    """

    def __init__(self, d_model: int, d_ff: int, dropout: float = 0.0):
        super().__init__()
        self.d_model = d_model
        self.d_ff = d_ff

        # Gate and up projections are fused for efficiency
        self.gate_proj = nn.Linear(d_model, d_ff, bias=False)
        self.up_proj   = nn.Linear(d_model, d_ff, bias=False)
        self.down_proj = nn.Linear(d_ff, d_model, bias=False)
        self.dropout   = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, d_model)
        Returns:
            out: (batch, seq_len, d_model)
        """
        # SwiGLU: SiLU(gate) ⊙ up, then project down
        gate = F.silu(self.gate_proj(x))   # (B, T, d_ff)
        up   = self.up_proj(x)             # (B, T, d_ff)
        hidden = gate * up                 # element-wise gating
        hidden = self.dropout(hidden)
        return self.down_proj(hidden)      # (B, T, d_model)
