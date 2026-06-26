import os
import sys
import asyncio
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from kattappa_data_engine.pipeline.distill.orchestrator import DistillationOrchestrator
from kattappa_data_engine.pipeline.distill.judge import DistillationJudge
from kattappa_data_engine.pipeline.distill.filters import QualityControlLayer
from kattappa_data_engine.pipeline.distill.telugu_generator import TeluguDistillGenerator
from kattappa_data_engine.pipeline.distill.compiler import DistillationCompiler

def test_distillation_orchestrator():
    orchestrator = DistillationOrchestrator(use_mock=True)
    prompt_node = {"id": "test_1", "category": "engineering", "prompt": "Explain UART."}
    
    result = asyncio.run(orchestrator.fetch_teacher_outputs(prompt_node))
    
    assert result is not None
    assert result["id"] == "test_1"
    assert "teacher_chatgpt" in result
    assert "teacher_gemini" in result
    assert "teacher_claude" in result

def test_distillation_judge():
    judge = DistillationJudge(use_mock=True)
    
    response_node = {
        "id": "test_2",
        "category": "planning",
        "instruction": "Design database cluster.",
        "teacher_chatgpt": "ChatGPT logic content",
        "teacher_gemini": "Gemini architectural context",
        "teacher_claude": "Claude explanation content"
    }
    
    evaluated = judge.evaluate_and_synthesize(response_node)
    
    assert evaluated["composite_score"] > 0
    assert "final_response" in evaluated
    assert evaluated["teacher_disagreement"] is False

def test_novelty_and_hard_filters():
    qc = QualityControlLayer(similarity_threshold=0.95)
    
    # 1. Verify passes first text
    node_1 = {
        "category": "engineering",
        "composite_score": 8.5,
        "final_response": "This is a long description of the SPI serial bus protocol working mechanism."
    }
    assert qc.passes_hard_filters(node_1) is True
    assert qc.passes_novelty_filter(node_1) is True
    
    # 2. Verify duplicate drop
    node_2 = {
        "category": "engineering",
        "composite_score": 8.5,
        "final_response": "This is a long description of the SPI serial bus protocol working mechanism."
    }
    assert qc.passes_novelty_filter(node_2) is False

def test_telugu_generator():
    gen = TeluguDistillGenerator()
    prompts = gen.generate_prompts(count_per_track=2)
    
    assert len(prompts) == 6 # 3 tracks * 2 prompts each
    assert prompts[0]["track"] == "pure_telugu"
    assert prompts[2]["track"] == "roman_telugu"
    assert prompts[4]["track"] == "hybrid_telugu"

def test_compiler_pipeline():
    test_out = "/tmp/test_distillation_dataset.jsonl"
    if os.path.exists(test_out):
        os.remove(test_out)
        
    compiler = DistillationCompiler(use_mock=True, output_path=test_out)
    
    prompts = [
        {"id": "t1", "category": "engineering", "prompt": "Explain UART."},
        {"id": "t2", "category": "planning", "prompt": "Draft fault-tolerant system layout."}
    ]
    
    report = asyncio.run(compiler.compile_dataset(prompts))
    
    assert report["exported_samples"] == 2
    assert os.path.exists(test_out)
    assert os.path.exists(test_out.replace(".jsonl", "_manifest.json"))
    
    if os.path.exists(test_out):
        os.remove(test_out)
        os.remove(test_out.replace(".jsonl", "_manifest.json"))
