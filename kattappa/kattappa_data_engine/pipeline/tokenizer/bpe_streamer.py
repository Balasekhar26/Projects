import os
import json
import sys

# Add the parent directories to path so we can import BPETokenizer
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from ai_foundations.tokenization.bpe_tokenizer import BPETokenizer

class BPEStreamer:
    def __init__(self, vocab_file_path=None, target_vocab_size=320):
        self.tokenizer = BPETokenizer()
        self.vocab_file_path = vocab_file_path
        self.target_vocab_size = target_vocab_size
        
        # Load vocab from cache if exists
        if vocab_file_path and os.path.exists(vocab_file_path):
            self.load_tokenizer(vocab_file_path)
        else:
            print("Warning: BPE Tokenizer not loaded. Run train_on_corpus() first.")

    def save_tokenizer(self, filepath):
        """Saves BPE tokenizer merges to a JSON file."""
        # Convert tuple keys to strings for JSON serializability
        serializable_merges = {f"{k[0]},{k[1]}": v for k, v in self.tokenizer.merges.items()}
        data = {
            "merges": serializable_merges,
            "target_vocab_size": self.target_vocab_size
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Tokenizer merges saved successfully to {filepath}")

    def load_tokenizer(self, filepath):
        """Loads BPE tokenizer merges from a JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        serializable_merges = data.get("merges", {})
        self.target_vocab_size = data.get("target_vocab_size", 320)
        
        # Reconstruct merges
        self.tokenizer.merges = {}
        for k, v in serializable_merges.items():
            pair = tuple(map(int, k.split(',')))
            self.tokenizer.merges[pair] = v
            
        # Reconstruct vocab
        self.tokenizer.vocab = {i: bytes([i]) for i in range(256)}
        # Merges must be processed in order of token ID to reconstruct vocabulary properly
        sorted_merges = sorted(self.tokenizer.merges.items(), key=lambda x: x[1])
        for pair, new_id in sorted_merges:
            self.tokenizer.vocab[new_id] = self.tokenizer.vocab[pair[0]] + self.tokenizer.vocab[pair[1]]
            
        print(f"Tokenizer merges loaded successfully from {filepath}. Total vocab: {len(self.tokenizer.vocab)}")

    def train_on_corpus(self, corpus_text, filepath_to_save):
        """Trains BPE on the text and saves merges to file."""
        print(f"Training BPE Tokenizer (target size: {self.target_vocab_size})...")
        self.tokenizer.train(corpus_text, self.target_vocab_size)
        self.save_tokenizer(filepath_to_save)

    def encode(self, text):
        """Encodes text to BPE integer list."""
        return self.tokenizer.encode(text)

    def decode(self, ids):
        """Decodes BPE integer list back to text."""
        return self.tokenizer.decode(ids)

    def pack_tokens(self, token_ids, sequence_length=1024, eos_token_id=256):
        """
        Packs a continuous stream of tokens into chunks of sequence_length.
        Pads shorter sequences or separates documents with eos_token_id.
        Returns a list of packed token sequences.
        """
        packed_sequences = []
        current_seq = []
        
        for token in token_ids:
            current_seq.append(token)
            if len(current_seq) == sequence_length:
                packed_sequences.append(current_seq)
                current_seq = []
                
        # Handle trailing tokens: pad with eos_token_id
        if current_seq:
            padding_len = sequence_length - len(current_seq)
            current_seq.extend([eos_token_id] * padding_len)
            packed_sequences.append(current_seq)
            
        return packed_sequences
