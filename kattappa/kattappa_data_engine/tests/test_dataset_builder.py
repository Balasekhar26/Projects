import os
import sys
import json
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.dataset_builder import DatasetBuilder

def test_dataset_builder_pipeline():
    test_output_dir = "/tmp/kattappa_sft_test"
    test_raw_jsonl = "/tmp/kattappa_synthetic_mock.jsonl"
    
    # Clean up test directories if they exist
    import shutil
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)
    if os.path.exists(test_raw_jsonl):
        os.remove(test_raw_jsonl)
        
    # Write a small mock raw dataset to test_raw_jsonl to keep test execution fast
    # 6 categories * 15 samples = 90 samples
    categories = ["reasoning", "planning", "coding", "memory", "tool_usage", "telugu"]
    mock_samples = []
    for i in range(90):
        cat = categories[i % len(categories)]
        mock_samples.append({
            "id": f"mock_{i}",
            "category": cat,
            "difficulty": "medium",
            "language": "english" if cat != "telugu" else "roman_telugu",
            "question": f"Question {i} for category {cat}",
            "solution_outline": f"Outline step for {i}",
            "answer": f"Answer response {i}",
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["mock"],
            "estimated_tokens": 120
        })
        
    with open(test_raw_jsonl, 'w', encoding='utf-8') as f:
        for sample in mock_samples:
            f.write(json.dumps(sample) + "\n")
            
    # Run the builder with mocks
    builder = DatasetBuilder(output_dir=test_output_dir, raw_jsonl_path=test_raw_jsonl)
    train_samples, val_splits = builder.build_sft_dataset()
    
    # Assert output files exist
    assert os.path.exists(test_output_dir)
    assert os.path.exists(os.path.join(test_output_dir, "train.jsonl"))
    assert os.path.exists(os.path.join(test_output_dir, "dataset_manifest.json"))
    
    # Check that format of train.jsonl is correct
    required_keys = {"instruction", "input", "output", "category", "difficulty", "language"}
    train_inst_count = 0
    with open(os.path.join(test_output_dir, "train.jsonl"), 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            assert required_keys.issubset(item.keys())
            assert item["input"] == ""
            assert len(item["instruction"].strip()) > 0
            assert len(item["output"].strip()) > 0
            train_inst_count += 1
            
    # Verify replay and refusal data got created and mixed in
    categories_found = set()
    for sample in train_samples:
        categories_found.add(sample["category"])
        
    assert "general" in categories_found
    assert "refusal" in categories_found
    
    # Verify per-category validation files exist and conform to schema
    for cat in ["reasoning", "planning", "coding", "memory", "tool_usage", "telugu", "general", "refusal"]:
        val_path = os.path.join(test_output_dir, f"validation_{cat}.jsonl")
        assert os.path.exists(val_path)
        with open(val_path, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                assert required_keys.issubset(item.keys())
                assert item["category"] == cat
                
    # Clean up test directories
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)
    if os.path.exists(test_raw_jsonl):
        os.remove(test_raw_jsonl)
