import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.dedup.exact_hash import ExactDeduplicator
from pipeline.dedup.minhash_lsh import MinHashLSH

def test_exact_dedup():
    dedup = ExactDeduplicator()
    hash1 = "sha256_mock_hash_value_1"
    hash2 = "sha256_mock_hash_value_2"
    
    assert dedup.is_duplicate(hash1) == False
    assert dedup.is_duplicate(hash1) == True
    assert dedup.is_duplicate(hash2) == False
    assert dedup.is_duplicate(hash2) == True

def test_code_normalization():
    lsh = MinHashLSH()
    code_with_comments = """
    # This is a Python comment
    def solve(x):
        # another line comment
        x_val = x + 1  # end line comment
        \"\"\"docstring explanation\"\"\"
        return x_val
    """
    normalized = lsh.normalize_code(code_with_comments)
    assert "#" not in normalized
    assert "docstring" not in normalized
    assert "def solve(x): x_val = x + 1 return x_val" in normalized or "x_val = x + 1" in normalized

def test_minhash_lsh_clustering():
    lsh = MinHashLSH(jaccard_threshold=0.80)
    
    # We use identical/highly similar strings
    text1 = "The brown fox jumped over the fence to escape the dog."
    text2 = "The brown fox jumped over the fence to escape the dog."
    text3 = "This is a completely different text sequence that has no similarity."
    
    # Signatures
    # Generate mock signatures for testing
    sig1 = [1, 2, 3, 4] * 32
    sig2 = [1, 2, 3, 4] * 32
    sig3 = [9, 9, 9, 9] * 32
    
    lsh.add_document("doc1", text1, sig1)
    lsh.add_document("doc2", text2, sig2)
    lsh.add_document("doc3", text3, sig3)
    
    clusters = lsh.get_duplicate_clusters()
    # doc1 and doc2 should be clustered together
    assert "doc1" in clusters or "doc2" in clusters
    # doc3 should not be in the same cluster
    grouped_with_doc3 = False
    for root, ids in clusters.items():
        if "doc3" in ids and ("doc1" in ids or "doc2" in ids):
            grouped_with_doc3 = True
    assert not grouped_with_doc3

def test_paragraph_frequency_filter():
    lsh = MinHashLSH()
    text = "Intro Paragraph.\n\nThis is a repeating boilerplate line that contains more than eighty characters to satisfy the length threshold.\n\nOutro Paragraph."
    
    # First time processing - keeps the repeating boilerplate
    clean1 = lsh.process_paragraphs_and_dedup(text, max_repetition_count=1)
    assert "repeating boilerplate" in clean1
    
    # Second time processing - drops the boilerplate because it exceeds max_repetition_count=1
    clean2 = lsh.process_paragraphs_and_dedup(text, max_repetition_count=1)
    assert "repeating boilerplate" not in clean2
    assert "Intro Paragraph" in clean2
