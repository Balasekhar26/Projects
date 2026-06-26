import os
import sys
import shutil

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.run_pipeline import KDEPipeline

def test_pipeline_integration():
    # Setup temporary directories under the workspace for test execution
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/pipeline_config.yaml"))
    
    # Initialize pipeline
    pipeline = KDEPipeline(config_path=config_path)
    
    # Make sure we clean out any existing folders first to verify creation
    for folder in [pipeline.cleaned_dir, pipeline.safe_dir, pipeline.dedup_dir, pipeline.scored_dir, pipeline.shards_dir, pipeline.reports_dir]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            
    # Run the pipeline (generates mock files and processes them)
    # Set run_ablation to False for tests to keep test runs fast
    pipeline.run(generate_mock=True, run_ablation=False)
    
    # Assert Checkpoint Files exist
    assert os.path.exists(os.path.join(pipeline.cleaned_dir, "ingested.jsonl"))
    assert os.path.exists(os.path.join(pipeline.dedup_dir, "deduplicated.jsonl"))
    assert os.path.exists(os.path.join(pipeline.scored_dir, "scored.jsonl"))
    
    # Assert Binary Shards exist
    assert os.path.exists(os.path.join(pipeline.shards_dir, "train", "tokens.bin"))
    assert os.path.exists(os.path.join(pipeline.shards_dir, "train", "metadata.idx"))
    
    # Assert Reports exist
    assert os.path.exists(os.path.join(pipeline.reports_dir, "quality_reports", "quarantine_logs.json"))
    assert os.path.exists(os.path.join(pipeline.reports_dir, "quality_reports", "contamination_report.json"))
