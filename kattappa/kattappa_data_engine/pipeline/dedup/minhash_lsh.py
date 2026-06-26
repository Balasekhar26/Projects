import re
import hashlib
from collections import defaultdict

class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, i):
        if i not in self.parent:
            self.parent[i] = i
            return i
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j

    def get_groups(self):
        groups = defaultdict(list)
        for node in list(self.parent.keys()):
            root = self.find(node)
            groups[root].append(node)
        return dict(groups)


class MinHashLSH:
    def __init__(self, num_hashes=128, jaccard_threshold=0.85, b=16, r=8):
        self.num_hashes = num_hashes
        self.jaccard_threshold = jaccard_threshold
        # b bands, r rows. b * r must be <= num_hashes
        self.b = b
        self.r = r
        if self.b * self.r > self.num_hashes:
            raise ValueError(f"b ({self.b}) * r ({self.r}) cannot exceed num_hashes ({self.num_hashes})")
            
        # LSH Hash buckets: band_idx -> bucket_hash -> list of doc_ids
        self.buckets = [defaultdict(list) for _ in range(self.b)]
        
        # Disjoint set union for tracking duplicate clusters
        self.uf = UnionFind()
        
        # Keep track of shingles sets for verifying exact Jaccard similarity
        self.doc_shingles = {}
        
        # Global paragraph tracker for paragraph-level duplication
        self.paragraph_frequencies = defaultdict(int)

    def normalize_code(self, code_text):
        """
        Code-aware normalization: Removes comments, docstrings, formatting, 
        and normalizes spacing to detect code forks/clones.
        """
        # Remove multiline comments / docstrings (C-style /* */ and Python triple-quotes)
        code = re.sub(r'/\*.*?\*/', '', code_text, flags=re.DOTALL)
        code = re.sub(r'"""External.*?Source"""|"""Text.*?content"""|""".*?"""|\'\'\'.*?\'\'\'', '', code, flags=re.DOTALL)
        
        # Remove single-line comments (C-style // and Python/Shell-style #)
        code = re.sub(r'//.*', '', code)
        code = re.sub(r'#.*', '', code)
        
        # Collapse whitespace
        code = re.sub(r'\s+', ' ', code).strip()
        return code

    def get_shingles(self, text, is_code=False, k=5):
        """Generates shingles set from text."""
        if is_code:
            text = self.normalize_code(text)
        else:
            text = re.sub(r'\s+', ' ', text).lower().strip()
            
        if len(text) < k:
            return {text}
        return {text[i:i+k] for i in range(len(text) - k + 1)}

    def add_document(self, doc_id, text, minhash_signature, is_code=False):
        """
        Indexes a document, finds near-duplicates, and links them 
        into duplicate groups.
        """
        is_duplicate_found = False
        # Store shingles for validation
        shingles = self.get_shingles(text, is_code=is_code)
        self.doc_shingles[doc_id] = shingles
        
        candidates = set()
        
        # Query bands to find candidates
        for band_idx in range(self.b):
            start = band_idx * self.r
            end = start + self.r
            band_sig = tuple(minhash_signature[start:end])
            
            # MD5 hash of band signature to get a bucket key
            bucket_key = hashlib.md5(str(band_sig).encode('utf-8')).hexdigest()
            
            # Retrieve prior documents colliding in this band
            for cand_id in self.buckets[band_idx][bucket_key]:
                candidates.add(cand_id)
                
            # Add current doc_id to the bucket
            self.buckets[band_idx][bucket_key].append(doc_id)
            
        # Verify exact Jaccard similarity for all candidates
        for cand_id in candidates:
            if cand_id == doc_id:
                continue
            
            cand_shingles = self.doc_shingles.get(cand_id)
            if cand_shingles:
                intersection = len(shingles.intersection(cand_shingles))
                union = len(shingles.union(cand_shingles))
                jaccard = intersection / union if union > 0 else 0.0
                
                # If Jaccard similarity exceeds threshold, record collision
                if jaccard >= self.jaccard_threshold:
                    self.uf.union(doc_id, cand_id)
                    is_duplicate_found = True
                    
        return is_duplicate_found

    def process_paragraphs_and_dedup(self, text, max_repetition_count=3):
        """
        Scans paragraph sequences inside the document.
        Reduces/filters paragraphs repeating above max_repetition_count.
        Helps prune legal footers and license boilerplate.
        Returns the deduplicated text.
        """
        paragraphs = text.split('\n\n')
        cleaned_paragraphs = []
        
        for para in paragraphs:
            para_clean = para.strip()
            if len(para_clean) < 80:  # Skip tracking very short lines
                cleaned_paragraphs.append(para)
                continue
                
            # Normalize paragraph representation to match duplicates
            para_norm = re.sub(r'\s+', ' ', para_clean).lower()
            para_hash = hashlib.md5(para_norm.encode('utf-8')).hexdigest()
            
            # Increment global repetition frequency
            self.paragraph_frequencies[para_hash] += 1
            
            # Keep paragraph only if under the frequency cap
            if self.paragraph_frequencies[para_hash] <= max_repetition_count:
                cleaned_paragraphs.append(para)
                
        return '\n\n'.join(cleaned_paragraphs)

    def get_duplicate_clusters(self):
        """Returns mapping of root_id -> list of document_ids in that cluster."""
        return self.uf.get_groups()
