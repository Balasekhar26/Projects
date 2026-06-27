import os
import json
import random
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    HAS_HF = True
except ImportError:
    HAS_HF = False


class MemoryBenchmark:
    def __init__(self, model=None, tokenizer=None, device="cpu"):
        """
        model: HuggingFace model instance or None (for mock simulation testing).
        tokenizer: HuggingFace tokenizer instance or None.
        device: Target execution device.
        """
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        
        # Build memory probe templates
        self.colors = ["blue", "green", "red", "yellow", "black", "white", "purple", "orange"]
        self.names = ["Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona"]
        self.projects = ["Aegis", "Beacon", "Chronos", "Daedalus"]
        
    def generate_probes(self):
        """Generates 100 memory validation probes covering all 6 dimensions."""
        random.seed(42)
        probes = []
        
        # MB-1 & MB-2: Store & Recall (20 probes)
        for i in range(20):
            name = random.choice(self.names)
            color = random.choice(self.colors)
            probes.append({
                "id": f"mb_store_recall_{i}",
                "dimension": "store_recall",
                "turns": [
                    {"role": "user", "content": f"My name is {name} and my favorite color is {color}.", "type": "store"},
                    {"role": "assistant", "content": "Noted. I will remember that.", "type": "ack"},
                    {"role": "user", "content": f"What is my favorite color?", "type": "recall", "expected": color}
                ]
            })
            
        # MB-3: Update (20 probes)
        for i in range(20):
            project = random.choice(self.projects)
            lead1 = random.choice(self.names)
            lead2 = random.choice([n for n in self.names if n != lead1])
            probes.append({
                "id": f"mb_update_{i}",
                "dimension": "update",
                "turns": [
                    {"role": "user", "content": f"The manager for Project {project} is {lead1}.", "type": "store"},
                    {"role": "assistant", "content": "Understood.", "type": "ack"},
                    {"role": "user", "content": f"Update: The manager for Project {project} is now {lead2}.", "type": "update"},
                    {"role": "assistant", "content": "Updated manager details.", "type": "ack"},
                    {"role": "user", "content": f"Who is the manager for Project {project}?", "type": "recall", "expected": lead2}
                ]
            })
            
        # MB-4: Forget (20 probes)
        for i in range(20):
            name = random.choice(self.names)
            city = "Guntur" if i % 2 == 0 else "Hyderabad"
            probes.append({
                "id": f"mb_forget_{i}",
                "dimension": "forget",
                "turns": [
                    {"role": "user", "content": f"I live in {city}.", "type": "store"},
                    {"role": "assistant", "content": "Noted.", "type": "ack"},
                    {"role": "user", "content": "Forget where I live.", "type": "forget"},
                    {"role": "assistant", "content": "I have forgotten that information.", "type": "ack"},
                    {"role": "user", "content": "Where do I live?", "type": "recall", "expected": "forgot"}
                ]
            })
            
        # MB-5: Conflict Resolution (20 probes)
        for i in range(20):
            date1 = f"March {random.randint(1, 10)}"
            date2 = f"March {random.randint(11, 20)}"
            probes.append({
                "id": f"mb_conflict_{i}",
                "dimension": "conflict_resolution",
                "turns": [
                    {"role": "user", "content": f"The milestone deadline is {date1}.", "type": "store"},
                    {"role": "assistant", "content": "Noted.", "type": "ack"},
                    {"role": "user", "content": f"Actually, the milestone deadline changed to {date2}.", "type": "store"},
                    {"role": "assistant", "content": "Updated deadline.", "type": "ack"},
                    {"role": "user", "content": "When is the milestone deadline?", "type": "recall", "expected": date2}
                ]
            })
            
        # MB-6: Long-Horizon Recall (20 probes)
        noise_queries = [
            "What is the CPU speed?", "Tell me a programming joke.", "What is 15 + 35?", 
            "Explain what a mutex is.", "How many bytes in a kilobyte?", "What is standard baud rate?"
        ]
        noise_answers = [
            "CPU speed varies by model.", "There are 10 types of people in the world...", "50.", 
            "A mutual exclusion lock.", "1024 bytes.", "9600 baud."
        ]
        
        for i in range(20):
            code = f"A{random.randint(100, 999)}"
            probe = {
                "id": f"mb_long_horizon_{i}",
                "dimension": "long_horizon",
                "turns": [
                    {"role": "user", "content": f"My access code is {code}.", "type": "store"},
                    {"role": "assistant", "content": "Noted.", "type": "ack"}
                ]
            }
            
            # Insert 12 turns of unrelated conversation (6 exchanges)
            for k in range(6):
                q = noise_queries[k % len(noise_queries)]
                ans = noise_answers[k % len(noise_answers)]
                probe["turns"].append({"role": "user", "content": q, "type": "noise"})
                probe["turns"].append({"role": "assistant", "content": ans, "type": "noise_ack"})
                
            # Final recall turn
            probe["turns"].append({"role": "user", "content": "What is my access code?", "type": "recall", "expected": code})
            probes.append(probe)
            
        return probes

    def run_generation(self, prompt, context_turns):
        """Helper to run causal generation from model or mock simulation."""
        if self.model is None or self.tokenizer is None:
            # Mock generator simulation for testing framework logic
            content = prompt.lower()
            if "update" in content:
                return "Updated manager details."
            if "forget" in content:
                return "I have forgotten that information."
                
            # Simple rule-based mock response to simulate recall
            if "color" in content:
                for color in self.colors:
                    if color in str(context_turns):
                        # 90% chance to return correct, 10% incorrect
                        return f"Your favorite color is {color}." if random.random() > 0.1 else "Your favorite color is red."
            if "manager" in content:
                for turn in reversed(context_turns):
                    for lead in self.names:
                        if lead in turn.get("content", ""):
                            return f"The manager is {lead}."
            if "where do i live" in content:
                # If forget action is present in context, simulate forgetting
                if "forget" in str(context_turns).lower():
                    return "I no longer have that information."
                for city in ["guntur", "hyderabad"]:
                    if city in str(context_turns).lower():
                        return f"You live in {city}."
            if "deadline" in content:
                # Match the last date mentioned in context
                dates = [d for d in ["March 1", "March 2", "March 3", "March 4", "March 5", "March 6", "March 7", "March 8", "March 9", "March 10", 
                                     "March 11", "March 12", "March 13", "March 14", "March 15", "March 16", "March 17", "March 18", "March 19", "March 20"]
                         if d.lower() in str(context_turns).lower()]
                if dates:
                    return f"The milestone deadline is {dates[-1]}."
            if "access code" in content:
                for c in ["A" + str(x) for x in range(100, 1000)]:
                    if c in str(context_turns):
                        # Simulating 80% recall over long horizon
                        return f"Your access code is {c}." if random.random() > 0.2 else "I don't remember."
                        
            return "I am noted."

        # Check if model is a custom PyTorch model (KattappaModel) and does not need Transformers
        if self.model.__class__.__name__ == "KattappaModel":
            history_str = ""
            for t in context_turns:
                history_str += f"{t['role']}: {t['content']}\n"
            history_str += f"user: {prompt}\nassistant:"
            
            inputs = self.tokenizer(history_str, return_tensors="pt").to(self.device)
            with torch.no_grad():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=64,
                    eos_id=self.tokenizer.eos_token_id
                )
            actual_out = self.tokenizer.decode(output_ids[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
            return actual_out

        if not HAS_HF:
            raise ImportError("PyTorch and Transformers libraries are required for real model inference.")

        # Real model inference using Chat Templates standard
        # Format conversation history
        messages = [{"role": t["role"], "content": t["content"]} for t in context_turns]
        messages.append({"role": "user", "content": prompt})
        
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([text], return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
        generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, generated_ids)]
        response = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return response

    def evaluate_model(self):
        print("Starting Memory Benchmark evaluation...")
        probes = self.generate_probes()
        results = {
            "store_recall": {"passed": 0, "failed": 0},
            "update": {"passed": 0, "failed": 0},
            "forget": {"passed": 0, "failed": 0},
            "conflict_resolution": {"passed": 0, "failed": 0},
            "long_horizon": {"passed": 0, "failed": 0}
        }
        
        report = []
        for p in probes:
            context = []
            dim = p["dimension"]
            
            # Execute all turns up to final recall
            for turn in p["turns"][:-1]:
                if turn["role"] == "user":
                    # Prompt the model (mock or real) and record its response
                    resp = self.run_generation(turn["content"], context)
                    context.append({"role": "user", "content": turn["content"]})
                    context.append({"role": "assistant", "content": resp})
                else:
                    # In SFT training we simulate gold standard context
                    context.append({"role": turn["role"], "content": turn["content"]})
                    
            # Final recall turn evaluation
            final_turn = p["turns"][-1]
            prompt = final_turn["content"]
            expected = final_turn["expected"]
            
            actual_response = self.run_generation(prompt, context)
            
            # Verification assertion check
            passed = False
            if expected == "forgot":
                # Check for forget terms
                forget_keywords = ["forget", "forgot", "no longer have", "don't know", "do not know"]
                passed = any(kw in actual_response.lower() for kw in forget_keywords)
            else:
                passed = expected.lower() in actual_response.lower()
                
            if passed:
                results[dim]["passed"] += 1
            else:
                results[dim]["failed"] += 1
                
            report.append({
                "probe_id": p["id"],
                "dimension": dim,
                "context": context,
                "prompt": prompt,
                "expected": expected,
                "actual": actual_response,
                "status": "PASSED" if passed else "FAILED"
            })
            
        # Compile final scores
        summary = {}
        for dim, counts in results.items():
            tot = counts["passed"] + counts["failed"]
            summary[f"{dim}_accuracy"] = round(counts["passed"] / tot, 4) if tot > 0 else 0.0
            
        final_report = {
            "summary": summary,
            "raw_counts": results,
            "probes_details": report
        }
        
        return final_report

if __name__ == "__main__":
    benchmark = MemoryBenchmark()
    report = benchmark.evaluate_model()
    print("="*60)
    print(" MEMORY BENCHMARK REPORT ".center(60, "="))
    print("="*60)
    print(json.dumps(report["summary"], indent=2))
