import numpy as np
from ai_foundations.attention.vector_math import matmul, softmax

class SingleHeadAttention:
    def __init__(self, d_model, d_k):
        self.d_model = d_model
        self.d_k = d_k
        self.scale = 1.0 / np.sqrt(d_k)
        
        # Initialize projection weights using a standard normal scaled distribution
        self.W_q = np.random.randn(d_model, d_k) * 0.02
        self.W_k = np.random.randn(d_model, d_k) * 0.02
        self.W_v = np.random.randn(d_model, d_k) * 0.02
        self.W_o = np.random.randn(d_k, d_model) * 0.02

    def forward(self, X, causal=True):
        """
        Executes the forward pass of Single-Head Attention.
        X shape: (B, T, d_model)
        Returns:
            output (B, T, d_model)
            attention_weights (B, T, T)
        """
        B, T, d_model = X.shape
        
        # 1. Project inputs into Query, Key, and Value spaces
        # (B, T, d_model) @ (d_model, d_k) -> (B, T, d_k)
        Q = matmul(X, self.W_q)
        K = matmul(X, self.W_k)
        V = matmul(X, self.W_v)
        
        # 2. Compute raw attention scores
        # (B, T, d_k) @ (B, d_k, T) -> (B, T, T)
        # We transpose the last two dimensions of K to do matrix multiply
        K_T = np.transpose(K, (0, 2, 1))
        scores = matmul(Q, K_T) * self.scale
        
        # 3. Apply causal masking
        if causal:
            # Create an upper-triangular mask of shape (T, T)
            mask = np.triu(np.ones((T, T)), k=1) * -1e9
            # Broadcast mask to batch size (B, T, T)
            scores = scores + mask
            
        # 4. Softmax to get attention weights
        weights = softmax(scores, axis=-1)
        
        # 5. Multiply weights by Values
        # (B, T, T) @ (B, T, d_k) -> (B, T, d_k)
        context = matmul(weights, V)
        
        # 6. Apply final output projection
        # (B, T, d_k) @ (d_k, d_model) -> (B, T, d_model)
        output = matmul(context, self.W_o)
        
        return output, weights
