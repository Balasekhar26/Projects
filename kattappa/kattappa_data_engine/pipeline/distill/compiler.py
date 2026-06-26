import os
import json
import asyncio
from typing import List, Dict, Any

from kattappa_data_engine.pipeline.distill.orchestrator import DistillationOrchestrator
from kattappa_data_engine.pipeline.distill.judge import DistillationJudge
from kattappa_data_engine.pipeline.distill.filters import QualityControlLayer
from kattappa_data_engine.pipeline.distill.telugu_generator import TeluguDistillGenerator

class DistillationCompiler:
    def __init__(self, use_mock: bool = True, output_path: str = None):
        self.orchestrator = DistillationOrchestrator(use_mock=use_mock)
        self.judge = DistillationJudge(use_mock=use_mock)
        self.qc = QualityControlLayer()
        self.output_path = output_path or os.path.abspath(os.path.join(
            os.path.dirname(__file__), "../../data/processed/distill/distillation_dataset.jsonl"
        ))

    async def compile_dataset(self, prompts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Orchestrates distillation pipeline from raw generation to filtered export."""
        print(f"Compiling distillation dataset with {len(prompts)} seed prompts...")
        
        # Create output folders
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        raw_outputs = []
        # Concurrently process in batches to prevent API rate limit overflows
        batch_size = 5
        for i in range(0, len(prompts), batch_size):
            batch = prompts[i:i+batch_size]
            tasks = [self.orchestrator.fetch_teacher_outputs(p) for p in batch]
            results = await asyncio.gather(*tasks)
            raw_outputs.extend(results)
            
        # Run Judge Layer & Filters
        final_samples = []
        disagreement_outliers = []
        filtered_out = 0
        
        for raw_node in raw_outputs:
            # 1. Score & Synthesize
            evaluated = self.judge.evaluate_and_synthesize(raw_node)
            
            # 2. Check Hard QC Floor
            if not self.qc.passes_hard_filters(evaluated):
                filtered_out += 1
                continue
                
            # 3. Check Outlier Arbitration
            if evaluated["teacher_disagreement"]:
                disagreement_outliers.append(evaluated)
                # Still export but flag for preference optimization DPO
            
            # 4. Check Novelty Filter
            if not self.qc.passes_novelty_filter(evaluated):
                filtered_out += 1
                continue
                
            final_samples.append(evaluated)
            
        # 5. Export JSONL
        with open(self.output_path, 'w', encoding='utf-8') as f:
            for sample in final_samples:
                f.write(json.dumps(sample) + "\n")
                
        # 6. Calculate Diversity Stats
        stats = self.qc.calculate_diversity_score(final_samples)
        
        report = {
            "total_prompts": len(prompts),
            "generated_samples": len(raw_outputs),
            "filtered_out": filtered_out,
            "exported_samples": len(final_samples),
            "disagreement_outliers": len(disagreement_outliers),
            "diversity_metrics": stats,
            "output_path": self.output_path
        }
        
        # Save manifest report
        report_path = self.output_path.replace(".jsonl", "_manifest.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
            
        return report

def run_distillation_build():
    """CLI orchestrator execution helper."""
    # Generate seed prompts
    telugu_gen = TeluguDistillGenerator()
    prompts = telugu_gen.generate_prompts(count_per_track=10) # 30 prompts total
    
    # Add other general/engineering seed prompts
    general_seeds = [
        {"id": "eng_1", "category": "engineering", "prompt": "Explain UART serial communication mechanism."},
        {"id": "eng_2", "category": "engineering", "prompt": "What are design trade-offs between SPI and I2C protocols?"},
        {"id": "reasoning_1", "category": "reasoning", "prompt": "A box has 3 red balls and 5 blue balls. If we draw 2, what is probability of same color?"},
        {"id": "planning_1", "category": "planning", "prompt": "Draft architectural roadmap to implement a fault-tolerant database replication cluster."}
    ]
    prompts.extend(general_seeds)
    
    compiler = DistillationCompiler(use_mock=True)
    report = asyncio.run(compiler.compile_dataset(prompts))
    
    print("\n" + "="*60)
    print(" DISTILLATION COMPILER COMPLETED ".center(60, "="))
    print("="*60)
    print(json.dumps(report, indent=2))
    print("="*60)
    return report

if __name__ == "__main__":
    run_distillation_build()
