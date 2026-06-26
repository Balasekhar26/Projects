import os
import sys
import json
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.synthetic.factory import SyntheticDataFactory

def test_synthetic_generation_and_schema():
    # Run the factory on a smaller target per category (e.g. 5) for quick unit-test speed
    # We will test the full size generation in the acceptance integration phase or verify it here.
    # To keep pytest execution fast, we run with target_per_category=10.
    test_output_path = "/tmp/kattappa_synthetic_test.jsonl"
    if os.path.exists(test_output_path):
        os.remove(test_output_path)
        
    factory = SyntheticDataFactory(output_filepath=test_output_path)
    samples = factory.generate_all(target_per_category=10)
    
    # Assert total count (6 categories * 10 samples = 60 samples)
    assert len(samples) == 60
    
    # Verify file exists
    assert os.path.exists(test_output_path)
    
    # Verify schema of each item
    required_keys = {
        "id", "category", "difficulty", "language", "question", 
        "solution_outline", "answer", "source", "generator", 
        "quality_score", "verified", "skills", "estimated_tokens"
    }
    
    categories_found = set()
    languages_found = set()
    
    with open(test_output_path, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            # Check all keys are present
            assert required_keys.issubset(item.keys()), f"Missing keys in schema: {required_keys - set(item.keys())}"
            
            # Check values are valid
            assert item["category"] in ["reasoning", "planning", "coding", "memory", "tool_usage", "telugu"]
            assert item["difficulty"] in ["easy", "medium", "hard"]
            assert item["language"] in ["english", "telugu", "roman_telugu"]
            assert len(item["question"].strip()) > 10
            assert len(item["answer"].strip()) > 10
            assert item["quality_score"] >= 0.90
            assert item["verified"] is True
            assert isinstance(item["skills"], list)
            assert item["estimated_tokens"] >= 50 # Minimum threshold
            
            categories_found.add(item["category"])
            languages_found.add(item["language"])
            
    # Verify all 6 categories generated
    assert len(categories_found) == 6
    # Verify Telugu/Roman Telugu languages are present
    assert "telugu" in languages_found or "roman_telugu" in languages_found
    
    # Clean up test file
    if os.path.exists(test_output_path):
        os.remove(test_output_path)
