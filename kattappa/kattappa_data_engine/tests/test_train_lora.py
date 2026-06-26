import os
import sys
import shutil
import subprocess
import pytest

def test_lora_training_dry_run():
    # Setup test paths
    output_dir = "kattappa-lora-v1"
    checkpoints_dir = "reports/checkpoints"
    
    # Clean up directories if they exist
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    if os.path.exists(checkpoints_dir):
        shutil.rmtree(checkpoints_dir)
        
    # Execute train_lora.py in dry-run mode using subprocess
    cmd = [
        sys.executable,
        "train_lora.py",
        "--dry-run"
    ]
    # Set PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = ".:kattappa_data_engine"
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env
    )
    
    # Assert successful execution
    assert result.returncode == 0, f"Training run failed with stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    
    # Assert required files exist under kattappa-lora-v1/
    assert os.path.exists(output_dir)
    assert os.path.exists(os.path.join(output_dir, "adapter_config.json"))
    assert os.path.exists(os.path.join(output_dir, "adapter_model.safetensors"))
    assert os.path.exists(os.path.join(output_dir, "training_metrics.json"))
    assert os.path.exists(os.path.join(output_dir, "evaluation_report.json"))
    assert os.path.exists(os.path.join(output_dir, "benchmark_history"))
    
    # Assert validation check outputs were saved to checkpoints directory
    assert os.path.exists(checkpoints_dir)
    assert os.path.exists(os.path.join(checkpoints_dir, "checkpoint_200.json"))
    assert os.path.exists(os.path.join(checkpoints_dir, "checkpoint_400.json"))
    assert os.path.exists(os.path.join(checkpoints_dir, "checkpoint_600.json"))
    
    # Clean up test directories
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    if os.path.exists(checkpoints_dir):
        shutil.rmtree(checkpoints_dir)
