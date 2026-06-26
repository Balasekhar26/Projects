import torch
import torch.nn as nn
from torch.nn import functional as F
import numpy as np
import random

# Set random seeds for reproducibility
torch.manual_seed(1337)
random.seed(1337)
np.random.seed(1337)

class TinyTransformerLM(nn.Module):
    """A tiny 1-layer autoregressive Transformer for fast ablation testing."""
    def __init__(self, vocab_size, n_embd=64, block_size=32):
        super().__init__()
        self.block_size = block_size
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        self.position_embedding_table = nn.Embedding(block_size, n_embd)
        
        # Self-attention head
        self.key = nn.Linear(n_embd, n_embd, bias=False)
        self.query = nn.Linear(n_embd, n_embd, bias=False)
        self.value = nn.Linear(n_embd, n_embd, bias=False)
        self.proj = nn.Linear(n_embd, n_embd)
        
        # Feed forward
        self.ffn = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd)
        )
        
        # Output layer
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size)

    def forward(self, idx, targets=None):
        B, T = idx.shape
        
        # Embed tokens and positions
        tok_emb = self.token_embedding_table(idx) # (B,T,C)
        pos_emb = self.position_embedding_table(torch.arange(T, device=idx.device)) # (T,C)
        x = tok_emb + pos_emb # (B,T,C)
        
        # Single Self-Attention layer
        x_ln = self.ln1(x)
        k = self.key(x_ln)   # (B,T,C)
        q = self.query(x_ln) # (B,T,C)
        # Compute attention scores ("affinities")
        wei = q @ k.transpose(-2, -1) * (k.shape[-1]**-0.5) # (B, T, T)
        # Causal mask to prevent looking ahead
        tril = torch.tril(torch.ones(T, T, device=idx.device))
        wei = wei.masked_fill(tril == 0, float('-inf'))
        wei = F.softmax(wei, dim=-1)
        # Apply attention to values
        v = self.value(x_ln) # (B,T,C)
        out = wei @ v # (B,T,C)
        x = x + self.proj(out)
        
        # Feed forward
        x = x + self.ffn(self.ln2(x))
        
        # Project to vocab
        logits = self.lm_head(x) # (B,T,vocab_size)
        
        loss = None
        if targets is not None:
            B, T, C = logits.shape
            logits_flat = logits.view(B*T, C)
            targets_flat = targets.view(B*T)
            loss = F.cross_entropy(logits_flat, targets_flat)
            
        return logits, loss


class AblationRunner:
    def __init__(self, vocab_size=1024, max_iters=150, batch_size=16, block_size=32):
        self.vocab_size = vocab_size
        self.max_iters = max_iters
        self.batch_size = batch_size
        self.block_size = block_size
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    def get_batch(self, data, batch_size, block_size):
        """Generates a small batch of data for training/evaluation."""
        ix = torch.randint(len(data) - block_size, (batch_size,))
        x = torch.stack([data[i:i+block_size] for i in ix])
        y = torch.stack([data[i+1:i+block_size+1] for i in ix])
        x, y = x.to(self.device), y.to(self.device)
        return x, y

    @torch.no_grad()
    def estimate_loss(self, model, eval_data, eval_iters=20):
        """Estimates loss over eval iterations."""
        model.eval()
        losses = torch.zeros(eval_iters)
        for k in range(eval_iters):
            x, y = self.get_batch(eval_data, self.batch_size, self.block_size)
            _, loss = model(x, y)
            losses[k] = loss.item()
        model.train()
        return losses.mean().item()

    def train_model(self, train_tokens, val_tokens):
        """Trains a tiny model on the given train tokens and returns validation perplexity."""
        # Convert lists to PyTorch tensors
        train_tensor = torch.tensor(train_tokens, dtype=torch.long)
        val_tensor = torch.tensor(val_tokens, dtype=torch.long)
        
        model = TinyTransformerLM(vocab_size=self.vocab_size, block_size=self.block_size)
        model.to(self.device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        
        # Train loop
        for step in range(self.max_iters):
            xb, yb = self.get_batch(train_tensor, self.batch_size, self.block_size)
            logits, loss = model(xb, yb)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            
        # Evaluate validation loss
        val_loss = self.estimate_loss(model, val_tensor)
        val_perplexity = np.exp(val_loss)
        return val_loss, val_perplexity

    def run_ablation(self, dataset_a_tokens, dataset_b_tokens, val_tokens, filter_name="Readability Filter"):
        """
        Runs the ablation test:
        Dataset A = with filter applied
        Dataset B = without filter applied (control group)
        """
        print(f"\n--- Running Ablation Experiment for: {filter_name} ---")
        print(f"Dataset A (Filtered)   | Size: {len(dataset_a_tokens)} tokens")
        print(f"Dataset B (Unfiltered) | Size: {len(dataset_b_tokens)} tokens")
        print(f"Held-out Validation    | Size: {len(val_tokens)} tokens")
        
        if len(dataset_a_tokens) < self.block_size + 1 or len(dataset_b_tokens) < self.block_size + 1:
            print("Error: Datasets are too small for ablation training. Skip ablation.")
            return None, None
            
        print("Training model on Dataset A (Filtered)...")
        loss_a, perp_a = self.train_model(dataset_a_tokens, val_tokens)
        print(f"Dataset A -> Val Loss: {loss_a:.4f} | Perplexity: {perp_a:.2f}")
        
        print("Training model on Dataset B (Unfiltered)...")
        loss_b, perp_b = self.train_model(dataset_b_tokens, val_tokens)
        print(f"Dataset B -> Val Loss: {loss_b:.4f} | Perplexity: {perp_b:.2f}")
        
        loss_diff = loss_b - loss_a
        print("-" * 50)
        print(f"Loss Delta (Unfiltered - Filtered): {loss_diff:.4f}")
        
        if loss_diff > 0.01:
            print(f"SUCCESS: Filter '{filter_name}' improved performance! Keep the filter.")
            return True, loss_diff
        else:
            print(f"WARNING: Filter '{filter_name}' did NOT improve validation loss significantly (Delta: {loss_diff:.4f}).")
            print("Recommendation: DISCARD OR TUNE FILTER to avoid unnecessary bias/loss of data diversity.")
            return False, loss_diff
