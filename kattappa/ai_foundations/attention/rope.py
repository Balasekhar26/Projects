import numpy as np

class RotaryPositionEmbedding:
    def __init__(self, dim, max_seq_len=2048, base=10000):
        """
        dim: Dimension size of each head (d_k). Must be even.
        max_seq_len: Maximum supported sequence length.
        base: Frequency scaling base (standard: 10000).
        """
        assert dim % 2 == 0, "Dimension for RoPE must be even"
        self.dim = dim
        self.max_seq_len = max_seq_len
        self.base = base
        
        # 1. Precompute theta frequencies: theta_i = base ** (-2i / dim)
        # We only need it for half of the dimensions because they rotate in pairs
        i = np.arange(0, dim, 2)
        self.theta = 1.0 / (base ** (i / dim))
        
        # 2. Precompute cos and sin matrices for max_seq_len
        m = np.arange(max_seq_len)
        # Outer product: shape (max_seq_len, dim/2)
        angles = np.outer(m, self.theta)
        
        # Duplicate each angle so that we have matching cos/sin for both elements of the pair
        # e.g., if angles is [a, b], we want [a, a, b, b]
        angles_duplicated = np.repeat(angles, 2, axis=-1) # shape (max_seq_len, dim)
        
        self.cos_cached = np.cos(angles_duplicated)
        self.sin_cached = np.sin(angles_duplicated)

    def apply_rope(self, x):
        """
        Applies Rotary Position Embeddings to tensor x.
        x shape: (B, H, T, d_k) where d_k == self.dim
        """
        B, H, T, d_k = x.shape
        assert d_k == self.dim, f"RoPE dimension mismatch: expected {self.dim}, got {d_k}"
        
        # Get cos and sin sliced to the current sequence length T
        # Shape: (T, d_k)
        cos = self.cos_cached[:T, :]
        sin = self.sin_cached[:T, :]
        
        # Expand dimensions for broadcasting over batch and head: (1, 1, T, d_k)
        cos = cos[np.newaxis, np.newaxis, :, :]
        sin = sin[np.newaxis, np.newaxis, :, :]
        
        # Create x_tilde = [-x_1, x_0, -x_3, x_2, ...]
        x_tilde = np.zeros_like(x)
        x_tilde[..., 0::2] = -x[..., 1::2]
        x_tilde[..., 1::2] = x[..., 0::2]
        
        # Compute rotated output
        return x * cos + x_tilde * sin
