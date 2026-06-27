import os
import tempfile
import json
import pytest
from pathlib import Path

import torch

from run_eval import run_health_check
from kattappa_native.training.model_card_generator import generate_model_card
from kattappa_native.training.experiment_registry import log_experiment, get_configs_hash


# 1. Weight Integrity Health Check Verification
def test_health_check_validates_weights():
    # Healthy weights should pass
    state_dict = {
        "weight1": torch.tensor([0.5, -1.2, 0.0]),
        "weight2": torch.tensor([10.5, 99.2])
    }
    run_health_check(state_dict) # Should not raise
    
    # NaN weights should raise ValueError
    bad_state_dict_nan = {
        "weight1": torch.tensor([0.5, float('nan'), 0.0])
    }
    with pytest.raises(ValueError, match="NaN detected"):
        run_health_check(bad_state_dict_nan)
        
    # Inf weights should raise ValueError
    bad_state_dict_inf = {
        "weight1": torch.tensor([0.5, float('inf'), 0.0])
    }
    with pytest.raises(ValueError, match="Inf detected"):
        run_health_check(bad_state_dict_inf)


# 2. Model Card Generator Verification
def test_model_card_generation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ckpt_path = Path(tmp_dir) / "checkpoint_step_0001000.pt"
        # Dummy checkpoint file
        ckpt_path.touch()
        
        model_config = {"n_layers": 6, "d_model": 384, "vocab_size": 32000, "context_length": 1024}
        training_details = {"hardware": "Apple M4", "steps": 1000, "lr": 3e-4, "peak_memory_gb": 4.5, "val_ppl": 15.2}
        safety_gates = {
            "reasoning_accuracy": 0.82,
            "engineering_accuracy": 0.76,
            "memory_accuracy": 0.90,
            "tool_selection_accuracy": 0.93,
            "telugu_accuracy": 0.88,
            "forgetting_retention": 0.97
        }
        
        card_path = generate_model_card(
            checkpoint_path=str(ckpt_path),
            model_config=model_config,
            dataset_version="corpus-v1",
            training_details=training_details,
            safety_gates=safety_gates
        )
        
        assert os.path.exists(card_path), "Model card was not generated!"
        content = Path(card_path).read_text()
        assert "Kattappa-100M" in content
        assert "Total Parameters:" in content
        assert "Apple M4" in content
        assert "0.82" in content


# 3. Experiment Registry Logging Verification
def test_experiment_registry_logging():
    with tempfile.TemporaryDirectory() as tmp_configs:
        config_file = Path(tmp_configs) / "default.json"
        with open(config_file, "w") as f:
            json.dump({"sft_epochs": 3, "lora_rank": 8}, f)
            
        # Get hash
        config_hash = get_configs_hash(tmp_configs)
        assert config_hash != "unknown-configs-dir"
        
        # Log experiment
        scorecard = {"reasoning": 0.80, "engineering": 0.75}
        record = log_experiment(
            experiment_id="exp-test-01",
            configs_dir=tmp_configs,
            dataset_version="corpus-v1",
            tokenizer_version="tokenizer-v1",
            learning_rate_curve=[3e-4, 1e-4],
            loss_curve=[0.8, 0.3],
            evaluation_scorecard=scorecard,
            notes="Ignition validation run"
        )
        
        assert record["experiment_id"] == "exp-test-01"
        assert record["config_hash"] == config_hash
        assert record["evaluation_scorecard"]["reasoning"] == 0.80
        
        # Verify saved record file
        out_dir = Path(__file__).parent.parent.parent / "kattappa_data_engine/reports/experiments"
        out_file = out_dir / "exp-test-01.json"
        assert out_file.exists(), "Experiment record file not written!"
        
        # Clean up
        if out_file.exists():
            out_file.unlink()
