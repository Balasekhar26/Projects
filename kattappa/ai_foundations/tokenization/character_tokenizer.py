"""
Character-Level Tokenizer.

Maps individual unique characters to integer IDs.
"""

class CharacterTokenizer:
    def __init__(self):
        self.vocab = []
        self.char_to_id = {}
        self.id_to_char = {}

    def train(self, text: str):
        """Build the vocabulary from unique characters in the training text."""
        self.vocab = sorted(list(set(text)))
        self.char_to_id = {char: idx for idx, char in enumerate(self.vocab)}
        self.id_to_char = {idx: char for idx, char in enumerate(self.vocab)}

    def encode(self, text: str) -> list[int]:
        """Convert a string into a list of character integer IDs."""
        return [self.char_to_id[char] for char in text if char in self.char_to_id]

    def decode(self, ids: list[int]) -> str:
        """Reconstruct the original string from a list of character IDs."""
        return "".join(self.id_to_char[idx] for idx in ids if idx in self.id_to_char)
