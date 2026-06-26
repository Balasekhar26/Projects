import os
import time
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# --- KM-3.1: Scratch-built LayerNorm & Softmax in PyTorch ---
class ScratchLayerNorm(nn.Module):
    def __init__(self, d_model, eps=1e-5):
        super().__init__()
        self.eps = eps
        # Initialize gamma to 1s and beta to 0s
        self.weight = nn.Parameter(torch.ones(d_model))
        self.bias = nn.Parameter(torch.zeros(d_model))

    def forward(self, x):
        mean = x.mean(dim=-1, keepdim=True)
        var = x.var(dim=-1, keepdim=True, unbiased=False)
        x_norm = (x - mean) / torch.sqrt(var + self.eps)
        return x_norm * self.weight + self.bias

def scratch_softmax(x, dim=-1):
    max_x = torch.max(x, dim=dim, keepdim=True)[0]
    exp_x = torch.exp(x - max_x)
    return exp_x / torch.sum(exp_x, dim=dim, keepdim=True)


# --- KM-3.5: Scratch-built Rotary Position Embeddings (RoPE) ---
class ScratchRoPE(nn.Module):
    def __init__(self, dim, max_seq_len=2048, base=10000):
        super().__init__()
        self.dim = dim
        
        # Precompute theta frequencies: theta_i = base ** (-2i / dim)
        i = torch.arange(0, dim, 2, dtype=torch.float32)
        theta = 1.0 / (base ** (i / dim))
        
        # Precompute cos and sin frequencies over sequence positions
        m = torch.arange(max_seq_len, dtype=torch.float32)
        angles = torch.outer(m, theta)  # Shape: (max_seq_len, dim/2)
        
        # Duplicate each angle so that they pair up: [a, b] -> [a, a, b, b]
        angles_duplicated = torch.repeat_interleave(angles, 2, dim=-1) # Shape: (max_seq_len, dim)
        
        # Register as buffers (not parameters, but saved in state_dict)
        self.register_buffer("cos_cached", torch.cos(angles_duplicated))
        self.register_buffer("sin_cached", torch.sin(angles_duplicated))

    def forward(self, x):
        """
        x shape: (B, H, T, d_k)
        """
        B, H, T, d_k = x.shape
        cos = self.cos_cached[:T, :].view(1, 1, T, d_k)
        sin = self.sin_cached[:T, :].view(1, 1, T, d_k)
        
        # Create x_tilde = [-x_1, x_0, -x_3, x_2, ...]
        x_tilde = torch.zeros_like(x)
        x_tilde[..., 0::2] = -x[..., 1::2]
        x_tilde[..., 1::2] = x[..., 0::2]
        
        return x * cos + x_tilde * sin


# --- KM-3.2, 3.3, 3.4: Scratch-built Multi-Head Attention ---
class ScratchMultiHeadAttention(nn.Module):
    def __init__(self, d_model, num_heads):
        super().__init__()
        assert d_model % num_heads == 0, "d_model must be divisible by num_heads"
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        self.scale = 1.0 / math.sqrt(self.d_k)
        
        # Projection parameters
        self.W_q = nn.Linear(d_model, d_model, bias=False)
        self.W_k = nn.Linear(d_model, d_model, bias=False)
        self.W_v = nn.Linear(d_model, d_model, bias=False)
        self.W_o = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x, causal=True, rope_layer=None):
        B, T, d_model = x.shape
        
        # 1. Linear projections
        Q = self.W_q(x)
        K = self.W_k(x)
        V = self.W_v(x)
        
        # 2. Split into heads: (B, T, d_model) -> (B, H, T, d_k)
        Q = Q.view(B, T, self.num_heads, self.d_k).transpose(1, 2)
        K = K.view(B, T, self.num_heads, self.d_k).transpose(1, 2)
        V = V.view(B, T, self.num_heads, self.d_k).transpose(1, 2)
        
        # 3. Apply RoPE if present
        if rope_layer is not None:
            Q = rope_layer(Q)
            K = rope_layer(K)
            
        # 4. Compute scaled dot-product attention scores
        # (B, H, T, d_k) @ (B, H, d_k, T) -> (B, H, T, T)
        scores = torch.matmul(Q, K.transpose(-2, -1)) * self.scale
        
        # 5. Apply causal masking
        if causal:
            # Construct upper triangular mask
            mask = torch.triu(torch.ones(T, T, device=x.device), diagonal=1) * -1e9
            scores = scores + mask.view(1, 1, T, T)
            
        # 6. Softmax
        weights = scratch_softmax(scores, dim=-1)
        
        # 7. Apply weights to values: (B, H, T, T) @ (B, H, T, d_k) -> (B, H, T, d_k)
        context = torch.matmul(weights, V)
        
        # 8. Merge heads: (B, H, T, d_k) -> (B, T, d_model)
        context = context.transpose(1, 2).contiguous().view(B, T, d_model)
        
        # 9. Output projection
        return self.W_o(context), weights


# --- KM-3.6: Scratch-built Transformer Decoder Block ---
class ScratchTransformerBlock(nn.Module):
    def __init__(self, d_model, num_heads, mlp_ratio=4.0):
        super().__init__()
        self.ln1 = ScratchLayerNorm(d_model)
        self.attn = ScratchMultiHeadAttention(d_model, num_heads)
        self.ln2 = ScratchLayerNorm(d_model)
        
        # MLP Layer
        mlp_hidden = int(d_model * mlp_ratio)
        self.W_gate = nn.Linear(d_model, mlp_hidden)
        self.W_down = nn.Linear(mlp_hidden, d_model)

    def forward(self, x, causal=True, rope_layer=None):
        # Attention with Pre-LN and residual connection
        norm1 = self.ln1(x)
        attn_out, weights = self.attn(norm1, causal=causal, rope_layer=rope_layer)
        x = x + attn_out
        
        # MLP with Pre-LN, Swish (or SiLU) activation and residual connection
        norm2 = self.ln2(x)
        hidden = F.silu(self.W_gate(norm2))  # silu is mathematically equivalent to swish
        mlp_out = self.W_down(hidden)
        x = x + mlp_out
        
        return x, weights


# --- KM-3.7: TinyGPT Model Definition ---
class TinyGPT(nn.Module):
    def __init__(self, vocab_size, d_model=128, num_heads=4, num_layers=2, max_seq_len=256):
        super().__init__()
        self.max_seq_len = max_seq_len
        
        # Embeddings
        self.token_embeddings = nn.Embedding(vocab_size, d_model)
        
        # Stacked Blocks
        self.blocks = nn.ModuleList([
            ScratchTransformerBlock(d_model, num_heads) for _ in range(num_layers)
        ])
        
        # RoPE Layer
        self.rope_layer = ScratchRoPE(dim=d_model // num_heads, max_seq_len=max_seq_len)
        
        # Final Norm
        self.ln_f = ScratchLayerNorm(d_model)
        
        # Output Head
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)
        
        # Share weights between embeddings and lm_head (weight tying standard)
        self.lm_head.weight = self.token_embeddings.weight

    def forward(self, token_ids, targets=None):
        B, T = token_ids.shape
        assert T <= self.max_seq_len, f"Sequence length {T} exceeds maximum of {self.max_seq_len}"
        
        # Embed tokens
        x = self.token_embeddings(token_ids)
        
        # Run stacked decoder blocks
        all_weights = []
        for block in self.blocks:
            x, weights = block(x, causal=True, rope_layer=self.rope_layer)
            all_weights.append(weights)
            
        # Final norm
        x = self.ln_f(x)
        
        # Logits
        logits = self.lm_head(x)
        
        # Compute loss if targets are provided
        loss = None
        if targets is not None:
            # Flatten outputs and targets for cross entropy computation
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
            
        return logits, loss, all_weights


# --- Custom Batch Loader for Training ---
class TokenDatasetLoader:
    def __init__(self, bin_path, batch_size=16, seq_len=64):
        self.batch_size = batch_size
        self.seq_len = seq_len
        
        # Load binary tokens into memory
        if os.path.exists(bin_path):
            self.tokens = np.fromfile(bin_path, dtype=np.uint16).astype(np.int64)
            print(f"Loaded {len(self.tokens)} tokens from {bin_path}")
        else:
            # Fallback to random data for testing if file missing
            print(f"Warning: {bin_path} not found. Generating dummy dataset.")
            self.tokens = np.random.randint(0, 320, size=20000, dtype=np.int64)

    def get_batch(self):
        # Pick random starting offsets
        ix = np.random.randint(0, len(self.tokens) - self.seq_len - 1, size=self.batch_size)
        x = torch.stack([torch.from_numpy(self.tokens[i : i + self.seq_len]) for i in ix])
        y = torch.stack([torch.from_numpy(self.tokens[i + 1 : i + self.seq_len + 1]) for i in ix])
        return x, y


# --- Main Training Loop Runner ---
def train_tiny_gpt():
    print("="*60)
    print(" STARTING TINY GPT TRAINING (KM-3.7) ".center(60, "="))
    print("="*60)
    
    # Vocabulary size match BPE tokenizer
    vocab_size = 320 
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Configure tiny model parameters
    model = TinyGPT(vocab_size=vocab_size, d_model=64, num_heads=4, num_layers=2, max_seq_len=128)
    model = model.to(device)
    
    # Load dataset
    bin_path = "kattappa_data_engine/data/shards/train/tokens.bin"
    loader = TokenDatasetLoader(bin_path, batch_size=8, seq_len=32)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    
    model.train()
    print("Training loop starting...")
    start_time = time.time()
    
    for step in range(50):
        x, y = loader.get_batch()
        x, y = x.to(device), y.to(device)
        
        optimizer.zero_grad()
        logits, loss, _ = model(x, y)
        loss.backward()
        
        # Clip grads to prevent explosions
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        
        if step % 10 == 0 or step == 49:
            perplexity = math.exp(loss.item()) if loss.item() < 20 else float('inf')
            print(f"Step {step:2d} | Loss: {loss.item():.4f} | Perplexity: {perplexity:.2f}")
            
    end_time = time.time()
    print(f"Training of 50 steps completed in {end_time - start_time:.2f} seconds.")
    
    # Save model checkpoint
    os.makedirs("models/checkpoints", exist_ok=True)
    torch.save(model.state_dict(), "models/checkpoints/tiny_gpt.pt")
    print("Model checkpoint saved to models/checkpoints/tiny_gpt.pt")

if __name__ == "__main__":
    train_tiny_gpt()
