class ExactDeduplicator:
    def __init__(self):
        self.seen_hashes = set()

    def is_duplicate(self, doc_hash):
        """Checks if the document hash has been seen, and indexes it if not."""
        if doc_hash in self.seen_hashes:
            return True
        self.seen_hashes.add(doc_hash)
        return False

    def reset(self):
        self.seen_hashes.clear()
