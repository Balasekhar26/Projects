import os
import json
import hashlib
from datetime import datetime, timezone
import re

# Custom MinHash signature function using standard Python hashlib/murmur-like hash functions
def get_shingles(text, k=5):
    """Generate character n-gram shingles of length k."""
    # Normalize whitespace for shingling
    normalized = re.sub(r'\s+', ' ', text).lower().strip()
    if len(normalized) < k:
        return {normalized}
    return {normalized[i:i+k] for i in range(len(normalized) - k + 1)}

def generate_minhash_signature(text, num_hashes=128):
    """
    Generate a MinHash signature for the text.
    Uses 128 hash functions mapping to integer values.
    Uses simple hashing coefficients to simulate random permutations.
    """
    shingles = get_shingles(text)
    signature = []
    
    # Pre-generate coefficients for random hash functions: h_i(x) = (a_i * x + b_i) % c
    # c is a prime number larger than the maximum hash value (2^32 - 1)
    c = 4294967311
    
    # We use stable deterministic coefficients based on hash index
    for i in range(num_hashes):
        a = (i * 10007 + 3) % c
        b = (i * 20011 + 7) % c
        
        min_val = float('inf')
        for shingle in shingles:
            # Hash the shingle to a 32-bit integer
            shingle_hash = int(hashlib.md5(shingle.encode('utf-8')).hexdigest()[:8], 16)
            # Permuted hash
            permuted = (a * shingle_hash + b) % c
            if permuted < min_val:
                min_val = permuted
                
        signature.append(int(min_val) if min_val != float('inf') else 0)
        
    return signature

class BaseExtractor:
    def __init__(self, pipeline_version="v1.0.0"):
        self.pipeline_version = pipeline_version

    def extract_document(self, content, source_path, macro_class, micro_class=None, license_tag="unknown", source_url=None, difficulty=5.0):
        """
        Takes raw text content and maps it to the KDE unified JSON schema.
        Generates fingerprints and tracks provenance.
        """
        # Cryptographic hash of content
        sha256_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # MinHash signature
        minhash_sig = generate_minhash_signature(content)
        
        # Basic stats
        char_count = len(content)
        line_count = len(content.splitlines())
        
        # Ingestion Timestamp
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Document ID based on hash
        doc_id = f"kde_doc_{sha256_hash[:16]}"
        
        doc = {
          "id": doc_id,
          "source": source_path,
          "content": content,
          "language": "unknown", # To be determined by language identifier stage
          "macro_class": macro_class,
          "micro_class": micro_class or macro_class,
          "provenance": {
            "source_id": os.path.basename(source_path),
            "source_url": source_url or "file://" + os.path.abspath(source_path),
            "license": license_tag,
            "ingestion_timestamp": timestamp,
            "pipeline_version": self.pipeline_version
          },
          "fingerprint": {
            "sha256": sha256_hash,
            "minhash_signature": minhash_sig
          },
          "metadata": {
            "char_count": char_count,
            "line_count": line_count,
            "difficulty": float(difficulty),
            "instruction": "",
            "response": "",
            "conversation": []
          }
        }
        return doc

    def process_file(self, filepath, macro_class, micro_class=None, license_tag="unknown", source_url=None, difficulty=5.0):
        """Reads a file and extracts it."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return self.extract_document(content, filepath, macro_class, micro_class, license_tag, source_url, difficulty)
        except Exception as e:
            # Return None to indicate extraction failure
            print(f"Error extracting {filepath}: {e}")
            return None
