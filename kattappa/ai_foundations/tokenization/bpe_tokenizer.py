"""
Byte-Pair Encoding (BPE) Tokenizer.

Implements byte-level BPE from scratch, mirroring the tokenization
design of modern LLMs (e.g. GPT-2/3/4).
Prevents out-of-vocabulary (<UNK>) issues by building on the 256 base bytes.
"""

def get_stats(ids: list[int]) -> dict[tuple[int, int], int]:
    """Calculate frequency of all adjacent token pairs."""
    counts = {}
    for pair in zip(ids, ids[1:]):
        counts[pair] = counts.get(pair, 0) + 1
    return counts

def merge(ids: list[int], pair: tuple[int, int], new_id: int) -> list[int]:
    """Replace all adjacent occurrences of 'pair' in 'ids' with 'new_id'."""
    new_ids = []
    i = 0
    while i < len(ids):
        if i < len(ids) - 1 and ids[i] == pair[0] and ids[i+1] == pair[1]:
            new_ids.append(new_id)
            i += 2
        else:
            new_ids.append(ids[i])
            i += 1
    return new_ids

class BPETokenizer:
    def __init__(self):
        # Base vocabulary maps token ID to byte representations
        self.vocab = {i: bytes([i]) for i in range(256)}
        # Merges map byte pairs to their new token ID
        self.merges = {}

    def train(self, text: str, vocab_size: int):
        """Train BPE on text by learning up to (vocab_size - 256) merge rules."""
        num_merges = vocab_size - 256
        if num_merges <= 0:
            return

        # Start with raw UTF-8 byte sequence representation
        ids = list(text.encode("utf-8"))

        for i in range(num_merges):
            stats = get_stats(ids)
            if not stats:
                break

            # Find the most frequent pair
            best_pair = max(stats, key=stats.get)
            # Only merge if the pair occurs more than once
            if stats[best_pair] <= 1:
                break

            new_id = 256 + len(self.merges)
            ids = merge(ids, best_pair, new_id)
            
            # Save the merge rule and update vocabulary
            self.merges[best_pair] = new_id
            self.vocab[new_id] = self.vocab[best_pair[0]] + self.vocab[best_pair[1]]

    def encode(self, text: str) -> list[int]:
        """Tokenize a string into BPE token IDs by applying learned merge rules in priority order."""
        ids = list(text.encode("utf-8"))
        while len(ids) >= 2:
            stats = get_stats(ids)
            # Find the learned merge rule that has the highest priority (lowest new_id)
            pair_to_merge = None
            min_new_id = float("inf")
            for pair in stats:
                if pair in self.merges:
                    if self.merges[pair] < min_new_id:
                        min_new_id = self.merges[pair]
                        pair_to_merge = pair

            if pair_to_merge is None:
                break # No more merge rules apply

            ids = merge(ids, pair_to_merge, min_new_id)
        return ids

    def decode(self, ids: list[int]) -> str:
        """Reconstruct the original string from BPE token IDs."""
        raw_bytes = b"".join(self.vocab.get(idx, b"") for idx in ids)
        return raw_bytes.decode("utf-8", errors="replace")
