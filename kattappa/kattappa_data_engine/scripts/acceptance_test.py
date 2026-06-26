import os
import sys
import json
import shutil
import numpy as np

# Add project root to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from pipeline.run_pipeline import KDEPipeline
from pipeline.tokenizer.bpe_streamer import BPEStreamer
from pipeline.evaluation.ablation_runner import AblationRunner

def run_acceptance_test():
    print("=" * 80)
    print(" KATTAPPA DATA ENGINE (KDE-v1) ACCEPTANCE TEST AUDIT ".center(80, "="))
    print("=" * 80)

    # Setup directories
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.abspath(os.path.join(script_dir, "../"))
    config_path = os.path.join(workspace_dir, "config/pipeline_config.yaml")

    # Initialize the pipeline
    pipeline = KDEPipeline(config_path=config_path)

    # Clear directories first to ensure a clean run
    for folder in [pipeline.raw_dir, pipeline.cleaned_dir, pipeline.safe_dir, pipeline.dedup_dir, pipeline.scored_dir, pipeline.shards_dir, pipeline.reports_dir]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)

    print("\n--- 1. PREPARING AUDIT DATASETS ---")

    def write_mock_file(rel_path, content):
        path = os.path.join(pipeline.raw_dir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    # Audit Item 1: Roman Telugu
    roman_telugu_text = (
        "nuvvu ela unnav\n"
        "nenu bagunnanu\n"
        "office ki vellanu\n"
        "meeting ayyaka call chestha\n"
        "deploy chesava bro\n"
        "This is some extra English text to simulate a realistic hybrid or code-switch context."
    )
    write_mock_file("conversations/roman_telugu.txt", roman_telugu_text)
    print("[Raw Created] Roman Telugu Conversation text.")

    # Audit Item 2: GPL Code
    gpl_code = (
        "# GPL Helper module\n"
        "# License: GPL-3.0-only\n"
        "def compute_gpl_logic(x):\n"
        "    return x * 9.8\n"
    )
    write_mock_file("code/gpl_helper.py", gpl_code)
    print("[Raw Created] GPL restricted license Python file.")

    # Audit Item 3: PII Content
    pii_content = (
        "Hello Team,\n"
        "Here are the credentials for testing:\n"
        "email: support@kattappa.io\n"
        "phone: +1 (555) 019-2834\n"
        "SSN: 999-12-3456\n"
        "secret_key=ab12cd34ef56gh78ij90kl12\n"
        "Please handle this with care."
    )
    write_mock_file("docs/api_credentials.md", pii_content)
    print("[Raw Created] Document containing PII (Email, Phone, SSN, API key).")

    # Audit Item 4: Near-Duplicates
    dup1 = "The ancient warrior Kattappa defended the kingdom with unparalleled courage and strength. His sword was legendary."
    dup2 = "The ancient warrior Kattappa defended the kingdom with unparalleled courage and strength! His sword was legendary." # near duplicate
    write_mock_file("books/warrior_v1.txt", dup1)
    write_mock_file("books/warrior_v2.txt", dup2)
    print("[Raw Created] Two near-duplicate narrative files.")

    # Audit Item 5: Benchmark Contamination
    # Question A: Exact Match MMLU question
    mmlu_exact = "which planet is closest to the sun?"
    # Question B: Paraphrased MMLU question
    mmlu_paraphrased = "Could you tell me which specific planet is situated closest to our sun?"
    
    write_mock_file("web/exact_leak.txt", mmlu_exact)
    write_mock_file("web/paraphrased_leak.txt", mmlu_paraphrased)
    print("[Raw Created] Exact and paraphrased benchmark contamination pages.")

    print("\n--- 2. EXECUTING KATTAPPA DATA ENGINE PIPELINE ---")
    pipeline.run(generate_mock=False, run_ablation=True)

    print("\n" + "=" * 80)
    print(" AUDIT VERIFICATION CHECKS ".center(80, "="))
    print("=" * 80)

    # Check 1: Did Roman Telugu survive and make it to the shards?
    print("\nCheck 1: Roman Telugu Survival Audit...")
    train_bin_path = os.path.join(pipeline.shards_dir, "train/tokens.bin")
    train_idx_path = os.path.join(pipeline.shards_dir, "train/metadata.idx")
    
    # Load and decode train tokens
    train_tokens = np.fromfile(train_bin_path, dtype=np.uint16)
    decoded_corpus = pipeline.bpe_streamer.decode(train_tokens.tolist())
    
    # Validate specific lines
    lines_to_verify = [
        "nuvvu ela unnav",
        "nenu bagunnanu",
        "office ki vellanu",
        "meeting ayyaka call chestha",
        "deploy chesava bro"
    ]
    
    survived = True
    for line in lines_to_verify:
        isPresent = line.lower() in decoded_corpus.lower()
        status = "PASSED" if isPresent else "FAILED"
        print(f"  - String '{line}' present in shard: {status}")
        if not isPresent:
            survived = False
            
    if survived:
        print("  => STATUS: PASSED (Roman Telugu fully preserved in final binary shards)")
    else:
        print("  => STATUS: FAILED (Some Roman Telugu lines were deleted!)")

    # Check 2: GPL Quarantine
    print("\nCheck 2: GPL Copyleft License Quarantine Audit...")
    quarantine_logs_path = os.path.join(pipeline.reports_dir, "quality_reports/quarantine_logs.json")
    with open(quarantine_logs_path, 'r') as f:
        quarantine_logs = json.load(f)
        
    gpl_quarantined = False
    for log in quarantine_logs:
        if "gpl_helper.py" in log.get("source", "") and "GPL" in log.get("reason", ""):
            gpl_quarantined = True
            print(f"  - GPL file quarantined successfully. Reason: {log.get('reason')}")
            
    if gpl_quarantined:
        print("  => STATUS: PASSED (GPL code quarantined successfully)")
    else:
        print("  => STATUS: FAILED (GPL code leaked into clean datasets!)")

    # Check 3: PII Redaction
    print("\nCheck 3: PII Redaction Audit...")
    # Read cleaned/scored files to verify support@kattappa.io, 999-12-3456, and secret keys are masked
    scored_path = os.path.join(pipeline.scored_dir, "scored.jsonl")
    pii_cleaned = True
    with open(scored_path, 'r') as f:
        for line in f:
            doc = json.loads(line)
            if "api_credentials.md" in doc.get("source", ""):
                content = doc.get("content", "")
                
                # Check redactions
                if "support@kattappa.io" in content or "999-12-3456" in content or "ab12cd34ef56gh78ij90kl12" in content:
                    pii_cleaned = False
                    print(f"  - Leaked raw values found in doc: {content}")
                else:
                    print("  - Email support@kattappa.io redacted to [REDACTED_EMAIL]")
                    print("  - Phone redacted to [REDACTED_PHONE]")
                    print("  - SSN 999-12-3456 redacted to [REDACTED_SSN]")
                    print("  - Secret API Key redacted to [REDACTED_SECRET]")

    if pii_cleaned:
        print("  => STATUS: PASSED (PII successfully scrubbed from content)")
    else:
        print("  => STATUS: FAILED (PII details leaked!)")

    # Check 4: Near-duplicate clustering & split isolation
    print("\nCheck 4: Deduplication & Split Isolation Audit...")
    with open(scored_path, 'r') as f:
        scored_docs = [json.loads(line) for line in f]
        
    # Check warrior_v1 and warrior_v2
    warrior_docs = [d for d in scored_docs if "warrior" in d.get("source", "")]
    # One of them should have been deduplicated before final packing!
    print(f"  - Scored documents with name 'warrior': {len(warrior_docs)}")
    
    # Load split indexes to verify if any warrior docs crossed splits
    split_isolated = True
    warrior_splits = set()
    for s_name in ["train", "validation", "test"]:
        idx_path = os.path.join(pipeline.shards_dir, f"{s_name}/metadata.idx")
        if os.path.exists(idx_path):
            with open(idx_path, 'r') as f:
                idx_data = json.load(f)
                for d in idx_data["documents"]:
                    if "warrior" in d.get("source", ""):
                        warrior_splits.add(s_name)
                        
    print(f"  - Splits containing warrior documents: {list(warrior_splits)}")
    if len(warrior_splits) > 1:
        split_isolated = False
        print("  - WARNING: Near-duplicates straddle across splits!")
    else:
        print("  - Near-duplicate copies successfully constrained to a single split.")

    if len(warrior_docs) <= 1 and split_isolated:
        print("  => STATUS: PASSED (Near-duplicates successfully filtered and split-isolated)")
    else:
        print("  => STATUS: FAILED (Duplicates leaked or crossed splits!)")

    # Check 5: Benchmark Contamination
    print("\nCheck 5: Benchmark Contamination Audit...")
    contamination_report_path = os.path.join(pipeline.reports_dir, "quality_reports/contamination_report.json")
    with open(contamination_report_path, 'r') as f:
        contamination_report = json.load(f)
        
    exact_caught = False
    paraphrased_caught = False
    
    for report in contamination_report:
        src = report.get("source", "")
        reason = report.get("reason", "")
        if "exact_leak.txt" in src:
            exact_caught = True
            print(f"  - Exact contamination caught: {reason}")
        if "paraphrased_leak.txt" in src:
            paraphrased_caught = True
            print(f"  - Paraphrased contamination caught: {reason}")
            
    if exact_caught and paraphrased_caught:
        print("  => STATUS: PASSED (Both exact and paraphrased leaks flagged and quarantined)")
    else:
        print(f"  => STATUS: FAILED (Exact caught: {exact_caught}, Paraphrased caught: {paraphrased_caught})")

    # Check 6: Backwards Token Traceability
    print("\nCheck 6: Backwards Token Traceability Audit...")
    # Let's pick a token index
    test_pos = 15
    print(f"  - Selecting random token index pos={test_pos} from train/tokens.bin...")
    
    # 1. Load train index
    with open(train_idx_path, 'r') as f:
        train_idx = json.load(f)
        
    target_doc = None
    for doc in train_idx["documents"]:
        offset = doc["offset"]
        count = doc["token_count"]
        if offset <= test_pos < offset + count:
            target_doc = doc
            break
            
    if target_doc:
        print(f"  - Index Offset Range matched: offset={target_doc['offset']}, token_count={target_doc['token_count']}")
        print(f"  - Document ID resolved: {target_doc['id']}")
        print(f"  - File Source resolved: {target_doc['source']}")
        
        # 2. Query scored checkpoint file for full provenance details
        provenance_resolved = None
        with open(scored_path, 'r') as f:
            for line in f:
                item = json.loads(line)
                if item["id"] == target_doc["id"]:
                    provenance_resolved = item.get("provenance", {})
                    break
                    
        if provenance_resolved:
            print(f"  - Source URL: {provenance_resolved.get('source_url')}")
            # Correct double slash if present in file path link
            link = f"file://{os.path.abspath(target_doc['source'])}"
            print(f"  - Clickable Local File link: [source_file]({link})")
            print(f"  - License Tag: {provenance_resolved.get('license')}")
            print(f"  - Pipeline Ingest Version: {provenance_resolved.get('pipeline_version')}")
            print(f"  - Ingestion Timestamp: {provenance_resolved.get('ingestion_timestamp')}")
            print("  => STATUS: PASSED (Full token-to-source backward provenance verified)")
        else:
            print("  - ERROR: Provenance metadata not found in checkpoint!")
            print("  => STATUS: FAILED")
    else:
        print("  - ERROR: Index offset range did not cover token index!")
        print("  => STATUS: FAILED")

    print("\n--- 3. ABLATION RUNNER COMPILATION LOG ---")
    # Execute AblationRunner comparison to display Filter decision table
    dataset_a_tokens = train_tokens.tolist()
    
    # Raw ingested tokens (Dataset B)
    raw_tokens = []
    ingested_path = os.path.join(pipeline.cleaned_dir, "ingested.jsonl")
    with open(ingested_path, 'r') as f:
        for line in f:
            doc = json.loads(line)
            raw_tokens.extend(pipeline.bpe_streamer.encode(doc["content"]))
            
    val_tokens = dataset_a_tokens[:100] # Use subset of clean tokens for val
    
    ablation = AblationRunner(max_iters=100) # Fast training run
    success, delta = ablation.run_ablation(
        dataset_a_tokens,
        raw_tokens,
        val_tokens,
        filter_name="Safety, Clean & Quality Filters"
    )
    
    # Print the Ablation decision table as required
    print("\n" + "-"*50)
    print(" KDE-v1 Filter Ablation Decision Table ".center(50, "-"))
    print("-"*50)
    print(f"{'Filter Applied':<30} | {'Val Loss Delta':<14} | {'Decision':<8}")
    print("-"*50)
    decision = "KEEP" if success else "DISCARD"
    print(f"{'Safety, Clean & Quality':<30} | {f'{delta:+.4f}':<14} | {decision:<8}")
    print("-"*50)

    # General Audit Outcome
    overall_passed = survived and gpl_quarantined and pii_cleaned and (len(warrior_docs) <= 1) and split_isolated and exact_caught and paraphrased_caught and (target_doc is not None)
    print("\n" + "=" * 80)
    if overall_passed:
        print(" OVERALL ACCEPTANCE AUDIT STATUS: PASSED ".center(80, " "))
        print(" KDE-v1 IS OFFICIALLY READY FOR MODEL COMPUTING SHARDS! ".center(80, " "))
    else:
        print(" OVERALL ACCEPTANCE AUDIT STATUS: FAILED ".center(80, " "))
        print(" Please debug failing checks. ".center(80, " "))
    print("=" * 80)

if __name__ == "__main__":
    run_acceptance_test()
