"""
KM-5.2 — RoPE Grouped-Query Self-Attention
========================================
Implements rotary positional embeddings (RoPE), Grouped-Query Attention (GQA),
and a persistent KV Cache for fast autoregressive decoder inference.
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


def repeat_kv(x: torch.Tensor, n_rep: int) -> torch.Tensor:
    """
    Repeat key/value heads for Grouped-Query Attention (GQA).
    x: (B, n_kv_heads, T, head_dim)
    n_rep: number of repetitions per head
    """
    if n_rep == 1:
        return x
    B, n_kv_heads, T, D = x.shape
    return x.unsqueeze(2).expand(B, n_kv_heads, n_rep, T, D).reshape(B, n_kv_heads * n_rep, T, D)


class MultiHeadAttention(nn.Module):
    """
    Causal Grouped-Query Self-Attention (GQA) with RoPE positional encoding and KV Cache.

    Args:
        d_model:    Model dimension (768 for Kattappa-100M).
        n_heads:    Number of query attention heads (12).
        n_kv_heads: Number of key/value heads (default: 4 for GQA).
        dropout:    Dropout on attention weights.
    """

    def __init__(self, d_model: int, n_heads: int, n_kv_heads: Optional[int] = 4, dropout: float = 0.0):
        super().__init__()
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"
        self.d_model = d_model
        self.n_heads = n_heads
        self.n_kv_heads = n_kv_heads if n_kv_heads is not None else n_heads
        self.group_size = n_heads // self.n_kv_heads
        self.head_dim = d_model // n_heads
        self.dropout = dropout

        # Projection sizes
        self.q_size = self.n_heads * self.head_dim
        self.kv_size = self.n_kv_heads * self.head_dim

        # Fused QKV projection for GQA efficiency
        self.qkv = nn.Linear(d_model, self.q_size + 2 * self.kv_size, bias=False)
        self.out_proj = nn.Linear(d_model, d_model, bias=False)

        self._attn_dropout = nn.Dropout(dropout)

        # Persistent Cache State for fast generation (resets per sequence)
        self.cache_k = None
        self.cache_v = None

    def reset_cache(self):
        """Clears the cached key and value tensors."""
        self.cache_k = None
        self.cache_v = None

    def forward(
        self,
        x: torch.Tensor,
        freqs_cis: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        use_cache: bool = False,
    ) -> torch.Tensor:
        """
        Args:
            x:         (batch, seq_len, d_model)
            freqs_cis: (seq_len, head_dim // 2) — RoPE frequencies for current steps
            mask:      (seq_len, total_seq_len) causal mask or None
            use_cache: If True, uses and updates persistent KV Cache
        Returns:
            out:       (batch, seq_len, d_model)
        """
        B, T, _ = x.shape
        H, H_kv, D = self.n_heads, self.n_kv_heads, self.head_dim

        # Project to Q, K, V
        qkv = self.qkv(x)  # (B, T, q_size + 2 * kv_size)
        q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)

        # Reshape to multi-head structures
        q = q.view(B, T, H, D)
        k = k.view(B, T, H_kv, D)
        v = v.view(B, T, H_kv, D)

        # Apply RoPE positional embeddings
        q = apply_rotary_emb(q, freqs_cis)
        k = apply_rotary_emb(k, freqs_cis)

        # Update / Load KV Cache
        if use_cache:
            if self.cache_k is None:
                self.cache_k = k
                self.cache_v = v
            else:
                self.cache_k = torch.cat([self.cache_k, k], dim=1)
                self.cache_v = torch.cat([self.cache_v, v], dim=1)
            k = self.cache_k
            v = self.cache_v

        # Transpose to (B, H/H_kv, seq_len, D) for attention
        q = q.transpose(1, 2)  # (B, H, T, D)
        k = k.transpose(1, 2)  # (B, H_kv, seq_len, D)
        v = v.transpose(1, 2)  # (B, H_kv, seq_len, D)

        # Repeat KV heads for Grouped-Query Attention (GQA)
        k = repeat_kv(k, self.group_size)  # (B, H, seq_len, D)
        v = repeat_kv(v, self.group_size)  # (B, H, seq_len, D)

        # Scaled dot-product attention
        scale = math.sqrt(D)
        attn = torch.matmul(q, k.transpose(-2, -1)) / scale  # (B, H, T, seq_len)

        if mask is not None:
            if mask.ndim == 2:
                mask = mask.unsqueeze(0).unsqueeze(1)
            attn = attn + mask

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
