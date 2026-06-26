import os
import json
import time

# Import all evaluators
from evaluation.reasoning_eval import ReasoningEvaluator
from evaluation.engineering_eval import EngineeringEvaluator
from evaluation.memory_eval import MemoryEvaluator
from evaluation.tool_eval import ToolEvaluator
from evaluation.telugu_eval import TeluguEvaluator
from evaluation.forgetting_eval import ForgettingEvaluator

def run_comprehensive_evaluation(model=None, tokenizer=None, device="cpu", output_path=None):
    print("="*70)
    print(" KATTAPPA-1B COMPREHENSIVE EVALUATION RUNNER ".center(70, "="))
    print("="*70)
    
    start_time = time.time()
    
    # 1. Reasoning Evaluation
    print("\nRunning Reasoning Evaluation...")
    reasoning_res = ReasoningEvaluator(model, tokenizer, device=device).evaluate()
    print(f"  Accuracy: {reasoning_res.get('reasoning_accuracy', 0.0) * 100:.2f}%")
    
    # 2. Engineering Evaluation
    print("Running Engineering/RF/Embedded Evaluation...")
    engineering_res = EngineeringEvaluator(model, tokenizer, device=device).evaluate()
    print(f"  Accuracy: {engineering_res.get('engineering_accuracy', 0.0) * 100:.2f}%")
    
    # 3. Memory Evaluation
    print("Running 6-Dimension Memory Evaluation...")
    memory_res = MemoryEvaluator(model, tokenizer, device=device).evaluate()
    print(f"  Aggregate Memory Accuracy: {memory_res.get('memory_aggregate_accuracy', 0.0) * 100:.2f}%")
    
    # 4. Tool Usage Evaluation
    print("Running Tool Calling & Syntax Evaluation...")
    tool_res = ToolEvaluator(model, tokenizer, device=device).evaluate()
    print(f"  JSON Validity: {tool_res.get('tool_json_validity', 0.0) * 100:.2f}%")
    print(f"  Tool Selection: {tool_res.get('tool_selection_accuracy', 0.0) * 100:.2f}%")
    print(f"  Argument Acc: {tool_res.get('tool_argument_accuracy', 0.0) * 100:.2f}%")
    
    # 5. Telugu / Script Adherence Evaluation
    print("Running Telugu/Code-Switching Evaluation...")
    telugu_res = TeluguEvaluator(model, tokenizer, device=device).evaluate()
    print(f"  Aggregate Telugu Accuracy: {telugu_res.get('telugu_aggregate_accuracy', 0.0) * 100:.2f}%")
    
    # 6. Forgetting / General Knowledge Evaluation
    print("Running Catastrophic Forgetting Evaluation...")
    forgetting_res = ForgettingEvaluator(model, tokenizer, device=device).evaluate()
    print(f"  General Knowledge Retention: {forgetting_res.get('general_forgetting_retention', 0.0) * 100:.2f}%")
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Aggregate Report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 2),
        "metrics": {
            "reasoning": reasoning_res.get("reasoning_accuracy", 0.0),
            "engineering": engineering_res.get("engineering_accuracy", 0.0),
            "memory": memory_res.get("memory_aggregate_accuracy", 0.0),
            "tool_selection": tool_res.get("tool_selection_accuracy", 0.0),
            "tool_json": tool_res.get("tool_json_validity", 0.0),
            "telugu": telugu_res.get("telugu_aggregate_accuracy", 0.0),
            "forgetting": forgetting_res.get("general_forgetting_retention", 0.0)
        },
        "breakdown": {
            "reasoning": reasoning_res,
            "engineering": engineering_res,
            "memory": memory_res,
            "tool": tool_res,
            "telugu": telugu_res,
            "forgetting": forgetting_res
        }
    }
    
    # Save Report to file
    out_file = output_path or os.path.abspath(os.path.join(
        os.path.dirname(__file__), "../kattappa_data_engine/reports/evaluation_report.json"
    ))
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
        
    print("\n" + "="*70)
    print(" EVALUATION REPORT SUMMARY ".center(70, "="))
    print("="*70)
    print(f"| {'Metric Dimension':<25} | {'Score':<10} | {'Status Gate':<15} |")
    print("-" * 59)
    
    gates = {
        "reasoning": (0.75, report["metrics"]["reasoning"]),
        "engineering": (0.70, report["metrics"]["engineering"]),
        "memory": (0.85, report["metrics"]["memory"]),
        "tool_selection": (0.90, report["metrics"]["tool_selection"]),
        "tool_json": (0.95, report["metrics"]["tool_json"]),
        "telugu": (0.85, report["metrics"]["telugu"]),
        "forgetting": (0.95, report["metrics"]["forgetting"])
    }
    
    for metric, (gate, val) in gates.items():
        status = "PASSED (GATE)" if val >= gate else "FAILED (GATE)"
        print(f"| {metric:<25} | {val * 100:>8.2f}% | {status:<15} |")
        
    print("="*70)
    print(f"Report saved to: {out_file}")
    
    return report

if __name__ == "__main__":
    run_comprehensive_evaluation()
