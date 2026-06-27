"""
KM-5.2 — Decoder Block
========================
A single pre-norm decoder block combining RoPE multi-head attention
and SwiGLU feed-forward with residual connections.

Structure:
    x → LayerNorm → Attention → + x  →  LayerNorm → MLP → + x
"""

import torch
import torch.nn as nn

from kattappa_native.model.attention import MultiHeadAttention
from kattappa_native.model.mlp import SwiGLUMLP


class DecoderBlock(nn.Module):
    """
    Single Kattappa decoder block.

    Args:
        d_model:   Model dimension.
        n_heads:   Number of attention heads.
        d_ff:      Feed-forward inner dimension.
        dropout:   Dropout rate applied in attention and MLP.
    """

    def __init__(self, d_model: int, n_heads: int, d_ff: int, n_kv_heads: Optional[int] = 4, dropout: float = 0.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attn  = MultiHeadAttention(d_model, n_heads, n_kv_heads=n_kv_heads, dropout=dropout)
        self.norm2 = nn.LayerNorm(d_model)
        self.mlp   = SwiGLUMLP(d_model, d_ff, dropout=dropout)

    def forward(self, x: torch.Tensor, freqs_cis: torch.Tensor,
                mask=None, use_cache: bool = False) -> torch.Tensor:
        """
        Args:
            x:         (batch, seq_len, d_model)
            freqs_cis: (seq_len, head_dim // 2) complex RoPE frequencies
            mask:      (seq_len, total_seq_len) causal mask or None
            use_cache: If True, uses and updates persistent KV Cache
        Returns:
            x:         (batch, seq_len, d_model)
        """
        # Pre-norm attention with residual
        x = x + self.attn(self.norm1(x), freqs_cis, mask=mask, use_cache=use_cache)
        # Pre-norm MLP with residual
        x = x + self.mlp(self.norm2(x))
        return x
