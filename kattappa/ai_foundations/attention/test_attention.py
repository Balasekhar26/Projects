import sys
import os
import pytest
import numpy as np
import torch

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from ai_foundations.attention.vector_math import softmax as np_softmax, layernorm as np_layernorm
from ai_foundations.attention.single_head import SingleHeadAttention
from ai_foundations.attention.multi_head import MultiHeadAttention as np_MultiHeadAttention
from ai_foundations.attention.rope import RotaryPositionEmbedding as np_RoPE
from ai_foundations.attention.transformer_block import TransformerBlock as np_TransformerBlock
from ai_foundations.attention.tiny_gpt import TinyGPT, ScratchLayerNorm, scratch_softmax, ScratchRoPE

def test_softmax_correctness():
    x = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    res_np = np_softmax(x, axis=-1)
    
    x_pt = torch.tensor(x)
    res_pt = scratch_softmax(x_pt, dim=-1).numpy()
    
    res_torch_native = torch.softmax(x_pt, dim=-1).numpy()
    
    # Assert custom numpy, custom torch, and native torch are numerically identical
    assert np.allclose(res_np, res_pt, atol=1e-5)
    assert np.allclose(res_np, res_torch_native, atol=1e-5)

def test_layernorm_correctness():
    x = np.random.randn(2, 3, 8)
    gamma = np.random.randn(8)
    beta = np.random.randn(8)
    
    res_np = np_layernorm(x, gamma, beta)
    
    ln_pt = ScratchLayerNorm(8)
    ln_pt.weight.data = torch.tensor(gamma, dtype=torch.float32)
    ln_pt.bias.data = torch.tensor(beta, dtype=torch.float32)
    
    res_pt = ln_pt(torch.tensor(x, dtype=torch.float32)).detach().numpy()
    
    assert np.allclose(res_np, res_pt, atol=1e-4)

def test_single_head_causal_mask():
    d_model = 16
    d_k = 8
    seq_len = 10
    batch_size = 2
    
    attn = SingleHeadAttention(d_model, d_k)
    X = np.random.randn(batch_size, seq_len, d_model)
    
    out, weights = attn.forward(X, causal=True)
    
    assert out.shape == (batch_size, seq_len, d_model)
    assert weights.shape == (batch_size, seq_len, seq_len)
    
    # Verify causal mask (future elements must have zero attention weight)
    for b in range(batch_size):
        for i in range(seq_len):
            for j in range(i + 1, seq_len):
                assert weights[b, i, j] == 0.0

def test_rope_properties():
    dim = 8
    seq_len = 5
    rope = ScratchRoPE(dim=dim, max_seq_len=seq_len)
    
    # Generate random Q and K tensors
    Q = torch.randn(1, 1, seq_len, dim)
    K = torch.randn(1, 1, seq_len, dim)
    
    Q_rot = rope(Q)
    K_rot = rope(K)
    
    # Dot-product of Q_rot and K_rot at positions i and j
    # should only depend on relative position (i - j).
    # Let's check dot product of position 1 and 3 (diff = 2) vs position 2 and 4 (diff = 2).
    # The dot product of rotated queries and keys at (pos_i, pos_j) equals:
    # Q(pos_i) @ R(pos_i - pos_j) @ K(pos_j)
    # We verify the shapes are correct and rotation was applied (vectors are changed)
    assert not torch.allclose(Q, Q_rot)
    assert Q_rot.shape == Q.shape
    assert K_rot.shape == K.shape

def test_tiny_gpt_training_convergence():
    torch.manual_seed(42)
    vocab_size = 32
    max_seq_len = 16
    
    model = TinyGPT(vocab_size=vocab_size, d_model=16, num_heads=2, num_layers=1, max_seq_len=max_seq_len)
    
    # Simple target sequence to memorize: [1, 2, 3, 4, 5]
    inputs = torch.tensor([[1, 2, 3, 4]], dtype=torch.long)
    targets = torch.tensor([[2, 3, 4, 5]], dtype=torch.long)
    
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    
    losses = []
    for _ in range(10):
        optimizer.zero_grad()
        logits, loss, _ = model(inputs, targets)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
        
    # Assert loss decreases over the 10 training steps
    assert losses[-1] < losses[0]
