import numpy as np
from ai_foundations.attention.vector_math import matmul, softmax

class MultiHeadAttention:
    def __init__(self, d_model, num_heads):
        assert d_model % num_heads == 0, "d_model must be divisible by num_heads"
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        self.scale = 1.0 / np.sqrt(self.d_k)
        
        # Initialize projection weights
        self.W_q = np.random.randn(d_model, d_model) * 0.02
        self.W_k = np.random.randn(d_model, d_model) * 0.02
        self.W_v = np.random.randn(d_model, d_model) * 0.02
        self.W_o = np.random.randn(d_model, d_model) * 0.02

    def forward(self, X, causal=True, rope_layer=None):
        """
        Executes the forward pass of Multi-Head Attention.
        X shape: (B, T, d_model)
        Returns:
            output (B, T, d_model)
            attention_weights (B, num_heads, T, T)
        """
        B, T, d_model = X.shape
        
        # 1. Linear projections
        # Shape: (B, T, d_model)
        Q = matmul(X, self.W_q)
        K = matmul(X, self.W_k)
        V = matmul(X, self.W_v)
        
        # 2. Reshape and Transpose to split into heads
        # (B, T, d_model) -> (B, T, H, d_k) -> (B, H, T, d_k)
        Q = Q.reshape(B, T, self.num_heads, self.d_k).transpose(0, 2, 1, 3)
        K = K.reshape(B, T, self.num_heads, self.d_k).transpose(0, 2, 1, 3)
        V = V.reshape(B, T, self.num_heads, self.d_k).transpose(0, 2, 1, 3)
        
        # 3. Apply Rotary Position Embeddings (RoPE) if provided
        if rope_layer is not None:
            Q = rope_layer.apply_rope(Q)
            K = rope_layer.apply_rope(K)
            
        # 4. Compute attention scores
        # (B, H, T, d_k) @ (B, H, d_k, T) -> (B, H, T, T)
        K_T = K.transpose(0, 1, 3, 2)
        scores = matmul(Q, K_T) * self.scale
        
        # 5. Apply causal masking
        if causal:
            mask = np.triu(np.ones((T, T)), k=1) * -1e9
            # Broadcast mask over batch and head dimensions: (B, H, T, T)
            scores = scores + mask[np.newaxis, np.newaxis, :, :]
            
        # 6. Softmax to get attention weights
        weights = softmax(scores, axis=-1)
        
        # 7. Apply weights to Values
        # (B, H, T, T) @ (B, H, T, d_k) -> (B, H, T, d_k)
        context = matmul(weights, V)
        
        # 8. Transpose and Reshape back to d_model
        # (B, H, T, d_k) -> (B, T, H, d_k) -> (B, T, d_model)
        context = context.transpose(0, 2, 1, 3).reshape(B, T, d_model)
        
        # 9. Apply output projection
        output = matmul(context, self.W_o)
        
        return output, weights
