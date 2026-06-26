import os
import sys

# Add project root to path to allow importing pipeline modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../kattappa_data_engine")))
from pipeline.memory_benchmark import MemoryBenchmark

class MemoryEvaluator:
    def __init__(self, model=None, tokenizer=None, device="cpu"):
        self.benchmark = MemoryBenchmark(model=model, tokenizer=tokenizer, device=device)

    def evaluate(self):
        """Runs the 6-dimension memory benchmark and collects metrics."""
        report = self.benchmark.evaluate_model()
        summary = report["summary"]
        
        return {
            "memory_store_recall_accuracy": summary.get("store_recall_accuracy", 0.0),
            "memory_update_accuracy": summary.get("update_accuracy", 0.0),
            "memory_forget_accuracy": summary.get("forget_accuracy", 0.0),
            "memory_conflict_resolution_accuracy": summary.get("conflict_resolution_accuracy", 0.0),
            "memory_long_horizon_accuracy": summary.get("long_horizon_accuracy", 0.0),
            "memory_aggregate_accuracy": round(sum(summary.values()) / len(summary), 4) if summary else 0.0
        }
