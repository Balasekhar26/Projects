import numpy as np
from ai_foundations.attention.vector_math import layernorm, matmul
from ai_foundations.attention.multi_head import MultiHeadAttention

def swish(x):
    """Swish activation function: x * sigmoid(x)"""
    return x / (1.0 + np.exp(-x))

class TransformerBlock:
    def __init__(self, d_model, num_heads, mlp_ratio=4.0):
        """
        d_model: Input / output token embedding dimension.
        num_heads: Number of attention heads.
        mlp_ratio: Expansion multiplier for the hidden MLP layer.
        """
        self.d_model = d_model
        self.num_heads = num_heads
        self.mlp_hidden_dim = int(d_model * mlp_ratio)
        
        # 1. Multi-Head Attention layer
        self.mha = MultiHeadAttention(d_model, num_heads)
        
        # 2. LayerNorm parameters (weights and biases initialized to 1s and 0s)
        self.gamma1 = np.ones(d_model)
        self.beta1 = np.zeros(d_model)
        self.gamma2 = np.ones(d_model)
        self.beta2 = np.zeros(d_model)
        
        # 3. MLP layer weights
        self.W_gate = np.random.randn(d_model, self.mlp_hidden_dim) * 0.02
        self.b_gate = np.zeros(self.mlp_hidden_dim)
        self.W_down = np.random.randn(self.mlp_hidden_dim, d_model) * 0.02
        self.b_down = np.zeros(d_model)

    def forward(self, X, causal=True, rope_layer=None):
        """
        Executes the forward pass of the Transformer Decoder block.
        X shape: (B, T, d_model)
        """
        # --- Stage 1: Attention Sub-Layer (Pre-LN style) ---
        norm1 = layernorm(X, self.gamma1, self.beta1)
        attn_out, weights = self.mha.forward(norm1, causal=causal, rope_layer=rope_layer)
        X_attn = X + attn_out  # Residual connection 1
        
        # --- Stage 2: MLP Sub-Layer (Pre-LN style) ---
        norm2 = layernorm(X_attn, self.gamma2, self.beta2)
        
        # MLP forward: Swish(norm2 @ W_gate + b_gate) @ W_down + b_down
        hidden = swish(matmul(norm2, self.W_gate) + self.b_gate)
        mlp_out = matmul(hidden, self.W_down) + self.b_down
        
        output = X_attn + mlp_out  # Residual connection 2
        
        return output, weights
