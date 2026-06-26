"""
KM-5.2 — RoPE Multi-Head Self-Attention
========================================
Implements rotary positional embeddings (RoPE) and causal
multi-head self-attention for the Kattappa-100M decoder.
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional


def precompute_freqs_cis(dim: int, max_seq_len: int, theta: float = 10000.0) -> torch.Tensor:
    """
    Precomputes complex exponentials for RoPE.
    Returns tensor of shape (max_seq_len, dim // 2) as complex64.
    """
    freqs = 1.0 / (theta ** (torch.arange(0, dim, 2, dtype=torch.float32) / dim))
    t = torch.arange(max_seq_len, dtype=torch.float32)
    freqs = torch.outer(t, freqs)  # (seq, dim/2)
    return torch.polar(torch.ones_like(freqs), freqs)  # complex64


def apply_rotary_emb(x: torch.Tensor, freqs_cis: torch.Tensor) -> torch.Tensor:
    """
    Apply RoPE to query or key tensor.
    x: (batch, seq_len, n_heads, head_dim)
    freqs_cis: (seq_len, head_dim // 2) complex
    """
    xq = torch.view_as_complex(x.float().reshape(*x.shape[:-1], -1, 2))
    freqs_cis = freqs_cis[:x.shape[1]].unsqueeze(0).unsqueeze(2)  # (1, seq, 1, head_dim/2)
    xq_out = torch.view_as_real(xq * freqs_cis).flatten(-2)
    return xq_out.to(x.dtype)


class MultiHeadAttention(nn.Module):
    """
    Causal multi-head self-attention with RoPE positional encoding.

    Args:
        d_model: Model dimension (768 for Kattappa-100M).
        n_heads: Number of attention heads (12).
        dropout: Dropout on attention weights (default 0.0 during inference).
    """

    def __init__(self, d_model: int, n_heads: int, dropout: float = 0.0):
        super().__init__()
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.dropout = dropout

        # Fused QKV projection for efficiency
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.out_proj = nn.Linear(d_model, d_model, bias=False)

        self._attn_dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        freqs_cis: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x:         (batch, seq_len, d_model)
            freqs_cis: (seq_len, head_dim // 2) — precomputed RoPE freqs
            mask:      (seq_len, seq_len) causal mask or None
        Returns:
            out:       (batch, seq_len, d_model)
        """
        B, T, _ = x.shape
        H, D = self.n_heads, self.head_dim

        # Project to Q, K, V
        qkv = self.qkv(x)  # (B, T, 3*d_model)
        q, k, v = qkv.split(self.d_model, dim=-1)  # each: (B, T, d_model)

        # Reshape to (B, T, H, D) for RoPE application
        q = q.view(B, T, H, D)
        k = k.view(B, T, H, D)
        v = v.view(B, T, H, D)

        # Apply RoPE to Q and K (not V)
        q = apply_rotary_emb(q, freqs_cis)
        k = apply_rotary_emb(k, freqs_cis)

        # Transpose to (B, H, T, D) for attention
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)

        # Scaled dot-product attention with causal mask
        scale = math.sqrt(D)
        attn = torch.matmul(q, k.transpose(-2, -1)) / scale  # (B, H, T, T)

        if mask is not None:
            attn = attn + mask  # additive causal mask (−inf for future tokens)

        attn = F.softmax(attn, dim=-1)
        attn = self._attn_dropout(attn)

        # Weighted sum of values
        out = torch.matmul(attn, v)  # (B, H, T, D)
        out = out.transpose(1, 2).contiguous().view(B, T, self.d_model)
        return self.out_proj(out)


def build_causal_mask(seq_len: int, device: torch.device) -> torch.Tensor:
    """Upper-triangular additive causal mask (−inf above diagonal)."""
    mask = torch.full((seq_len, seq_len), float("-inf"), device=device)
    return torch.triu(mask, diagonal=1)
