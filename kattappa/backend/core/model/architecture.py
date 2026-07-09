"""Kattappa Model Architecture (Program 27C).

Implements a decoder-only auto-regressive LLaMA-style transformer model:
Embedding -> N × DecoderBlock (RMSNorm + GQA/MHA + SwiGLU) -> RMSNorm -> LM Head.
"""
from __future__ import annotations

import math
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from backend.core.model.config import KattappaConfig


class KattappaRMSNorm(nn.Module):
    """Root Mean Square Layer Normalization (RMSNorm) for stable pre-normalization."""

    def __init__(self, dim: int, eps: float = 1e-6) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def _norm(self, x: torch.Tensor) -> torch.Tensor:
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self._norm(x.float()).type_as(x) * self.weight


def precompute_freqs_cis(dim: int, max_seq_len: int, theta: float = 10000.0) -> torch.Tensor:
    """Precomputes complex exponentials for Rotary Position Embeddings (RoPE)."""
    freqs = 1.0 / (theta ** (torch.arange(0, dim, 2, dtype=torch.float32) / dim))
    t = torch.arange(max_seq_len, dtype=torch.float32)
    freqs = torch.outer(t, freqs)  # (seq, dim // 2)
    return torch.polar(torch.ones_like(freqs), freqs)  # complex64


def apply_rotary_emb(x: torch.Tensor, freqs_cis: torch.Tensor) -> torch.Tensor:
    """Applies RoPE to a query or key tensor.

    x: (batch, seq_len, n_heads, head_dim)
    freqs_cis: (seq_len, head_dim // 2) complex
    """
    xq = torch.view_as_complex(x.float().reshape(*x.shape[:-1], -1, 2))
    freqs_cis = freqs_cis[: x.shape[1]].unsqueeze(0).unsqueeze(2)  # (1, seq, 1, head_dim/2)
    xq_out = torch.view_as_real(xq * freqs_cis).flatten(-2)
    return xq_out.to(x.dtype)


def repeat_kv(x: torch.Tensor, n_rep: int) -> torch.Tensor:
    """Repeats key/value heads for Grouped-Query Attention (GQA).

    x: (B, n_kv_heads, T, head_dim)
    n_rep: repetition count
    """
    if n_rep == 1:
        return x
    B, n_kv_heads, T, D = x.shape
    return x.unsqueeze(2).expand(B, n_kv_heads, n_rep, T, D).reshape(B, n_kv_heads * n_rep, T, D)


class KattappaAttention(nn.Module):
    """Grouped-Query Attention (GQA) / Multi-Head Self-Attention with RoPE and KV Cache."""

    def __init__(self, config: KattappaConfig) -> None:
        super().__init__()
        self.hidden_size = config.hidden_size
        self.num_attention_heads = config.num_attention_heads
        self.num_key_value_heads = config.num_key_value_heads or config.num_attention_heads
        self.group_size = self.num_attention_heads // self.num_key_value_heads
        self.head_dim = self.hidden_size // self.num_attention_heads

        self.q_proj = nn.Linear(self.hidden_size, self.num_attention_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(self.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(self.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(self.num_attention_heads * self.head_dim, self.hidden_size, bias=False)

        # Cache variables
        self.cache_k: Optional[torch.Tensor] = None
        self.cache_v: Optional[torch.Tensor] = None

    def reset_cache(self) -> None:
        self.cache_k = None
        self.cache_v = None

    def forward(
        self,
        x: torch.Tensor,
        freqs_cis: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        use_cache: bool = False,
    ) -> torch.Tensor:
        B, T, _ = x.shape
        H, H_kv, D = self.num_attention_heads, self.num_key_value_heads, self.head_dim

        q = self.q_proj(x).view(B, T, H, D)
        k = self.k_proj(x).view(B, T, H_kv, D)
        v = self.v_proj(x).view(B, T, H_kv, D)

        q = apply_rotary_emb(q, freqs_cis)
        k = apply_rotary_emb(k, freqs_cis)

        if use_cache:
            if self.cache_k is None:
                self.cache_k = k
                self.cache_v = v
            else:
                self.cache_k = torch.cat([self.cache_k, k], dim=1)
                self.cache_v = torch.cat([self.cache_v, v], dim=1)
            k = self.cache_k
            v = self.cache_v

        q = q.transpose(1, 2)  # (B, H, T, D)
        k = k.transpose(1, 2)  # (B, H_kv, seq_len, D)
        v = v.transpose(1, 2)  # (B, H_kv, seq_len, D)

        k = repeat_kv(k, self.group_size)  # (B, H, seq_len, D)
        v = repeat_kv(v, self.group_size)  # (B, H, seq_len, D)

        scale = 1.0 / math.sqrt(D)
        attn = torch.matmul(q, k.transpose(-2, -1)) * scale

        if mask is not None:
            if mask.ndim == 2:
                mask = mask.unsqueeze(0).unsqueeze(1)
            attn = attn + mask

        attn = F.softmax(attn, dim=-1)
        out = torch.matmul(attn, v)  # (B, H, T, D)
        out = out.transpose(1, 2).contiguous().view(B, T, self.hidden_size)
        return self.o_proj(out)


class KattappaMLP(nn.Module):
    """SwiGLU Multi-Layer Perceptron (gated feed-forward)."""

    def __init__(self, config: KattappaConfig) -> None:
        super().__init__()
        self.w1 = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)
        self.w2 = nn.Linear(config.intermediate_size, config.hidden_size, bias=False)
        self.w3 = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # SwiGLU equation: w2( SiLU(w1(x)) * w3(x) )
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class KattappaDecoderBlock(nn.Module):
    """Single pre-normalized decoder block combining self-attention and SwiGLU."""

    def __init__(self, config: KattappaConfig) -> None:
        super().__init__()
        self.norm1 = KattappaRMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.attn = KattappaAttention(config)
        self.norm2 = KattappaRMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.mlp = KattappaMLP(config)

    def forward(
        self,
        x: torch.Tensor,
        freqs_cis: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        use_cache: bool = False,
    ) -> torch.Tensor:
        x = x + self.attn(self.norm1(x), freqs_cis, mask=mask, use_cache=use_cache)
        x = x + self.mlp(self.norm2(x))
        return x


class KattappaModel(nn.Module):
    """Full auto-regressive transformer model with LM head."""

    def __init__(self, config: KattappaConfig) -> None:
        super().__init__()
        self.config = config

        self.tok_embeddings = nn.Embedding(config.vocab_size, config.hidden_size)
        self.layers = nn.ModuleList([KattappaDecoderBlock(config) for _ in range(config.num_hidden_layers)])
        self.norm = KattappaRMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.output = nn.Linear(config.hidden_size, config.vocab_size, bias=False)

        # Precompute frequencies for Rotary Position Embeddings
        self.freqs_cis = precompute_freqs_cis(
            dim=config.hidden_size // config.num_attention_heads,
            max_seq_len=config.max_position_embeddings * 2,
            theta=config.rope_theta,
        )

    def forward(
        self,
        tokens: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        use_cache: bool = False,
    ) -> torch.Tensor:
        _B, T = tokens.shape
        x = self.tok_embeddings(tokens)

        # Ensure freqs_cis is on the correct device and matches datatype
        self.freqs_cis = self.freqs_cis.to(device=tokens.device)
        freqs_cis = self.freqs_cis[:T]

        for layer in self.layers:
            x = layer(x, freqs_cis, mask=mask, use_cache=use_cache)

        x = self.norm(x)
        logits = self.output(x)
        return logits

    def reset_cache(self) -> None:
        for layer in self.layers:
            layer.attn.reset_cache()
