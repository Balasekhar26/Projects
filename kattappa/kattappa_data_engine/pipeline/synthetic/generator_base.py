import random

class BaseGenerator:
    def __init__(self, category_name):
        self.category_name = category_name

    def generate_id(self, idx):
        """Generates a structured ID for the training sample."""
        return f"km2_{self.category_name[:4]}_{idx:06d}"

    def estimate_tokens(self, *texts):
        """
        Estimates the token count based on typical character/word counts.
        Standard rule of thumb: ~4 characters per token or 0.75 words per token.
        """
        total_chars = sum(len(text) for text in texts if text)
        return max(10, int(total_chars / 3.8))

    def set_seed(self, seed_val):
        """Sets random seed for deterministic generation."""
        random.seed(seed_val)

    def generate_batch(self, count):
        """To be implemented by subclass. Returns a list of sample dicts."""
        raise NotImplementedError
