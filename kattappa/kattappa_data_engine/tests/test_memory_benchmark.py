import os
import sys
import json
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.memory_benchmark import MemoryBenchmark

def test_memory_benchmark_probes_and_scores():
    benchmark = MemoryBenchmark()
    probes = benchmark.generate_probes()
    
    # Assert total probes = 100
    assert len(probes) == 100
    
    # Assert expected dimensions exist
    dimensions = {p["dimension"] for p in probes}
    assert dimensions == {"store_recall", "update", "forget", "conflict_resolution", "long_horizon"}
    
    # Assert each dimension has exactly 20 probes
    dim_counts = {}
    for p in probes:
        dim_counts[p["dimension"]] = dim_counts.get(p["dimension"], 0) + 1
    for dim, count in dim_counts.items():
        assert count == 20
        
    # Run the evaluation under mock settings
    report = benchmark.evaluate_model()
    
    # Assert report structure keys
    assert "summary" in report
    assert "raw_counts" in report
    assert "probes_details" in report
    
    # Assert metrics contain accuracies
    summary = report["summary"]
    assert "store_recall_accuracy" in summary
    assert "update_accuracy" in summary
    assert "forget_accuracy" in summary
    assert "conflict_resolution_accuracy" in summary
    assert "long_horizon_accuracy" in summary
    
    # Verify accuracies are floats between 0 and 1
    for val in summary.values():
        assert 0.0 <= val <= 1.0
