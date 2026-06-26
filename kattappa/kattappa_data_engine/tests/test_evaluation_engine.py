import os
import sys
import json
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from evaluation.run_all import run_comprehensive_evaluation

def test_evaluation_engine_orchestration():
    test_report_path = "/tmp/evaluation_report_mock.json"
    if os.path.exists(test_report_path):
        os.remove(test_report_path)
        
    # Execute full evaluation runner on mock settings (no model/tokenizer provided)
    report = run_comprehensive_evaluation(output_path=test_report_path)
    
    # Assert output report file exists
    assert os.path.exists(test_report_path)
    
    # Verify contents of compiled report
    with open(test_report_path, 'r') as f:
        data = json.load(f)
        
    assert "timestamp" in data
    assert "elapsed_seconds" in data
    assert "metrics" in data
    assert "breakdown" in data
    
    # Assert specific metric gates are logged
    metrics = data["metrics"]
    required_metrics = {"reasoning", "engineering", "memory", "tool_selection", "tool_json", "telugu", "forgetting"}
    assert required_metrics.issubset(metrics.keys())
    
    # Verify values are floats
    for metric_name in required_metrics:
        assert isinstance(metrics[metric_name], float)
        assert 0.0 <= metrics[metric_name] <= 1.0
        
    # Clean up mock file
    if os.path.exists(test_report_path):
        os.remove(test_report_path)
