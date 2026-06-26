# Kattappa Model Program (KMP) — AI Foundations & Core Systems Engineering

This document establishes the definitive, production-first roadmap for building a Large Language Model and its surrounding cognitive operating system from scratch.

```
                  Kattappa OS Dual-Track Roadmap
  ┌─────────────────────────────────────────────────────────────┐
  │ Track A: Kattappa Core Evolution                            │
  │ (Cognitive Architecture, Memory, Planning, Verifiers, Tools)│
  └──────────────────────────────┬──────────────────────────────┘
                                 │ Generates Data & System Logs
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ Track B: Kattappa Model Program (KMP)                       │
  │ (Foundations ──> Architecture ──> Pre-train ──> Alignment)   │
  └─────────────────────────────────────────────────────────────┘
```

---

## 1. Core Architectural Strategy
The ultimate goal of the Kattappa project is to build a highly capable, local-first artificial intelligence assistant that serves as an operating system. To achieve this, we do not start by training a massive foundation model. Instead, we follow a dual-track strategy:

*   **Track A: Kattappa Core Evolution**: Continually build the cognitive architecture (planning engine, reflection loops, safety barriers, and semantic episodic memory) on top of existing frontier APIs (OpenAI, Claude, Gemini).
*   **Track B: Kattappa Model Program (KMP)**: Systematically learn neural networks, transformers, tokenization, pre-training, and alignment to eventually train a small, native, local model optimized specifically for the Kattappa Core OS.

---

## 2. Eleven Industry Misconceptions (The Reality Checks)

1.  **"Training, Fine-Tuning, RAG, and Prompting are interchangeable."**
    *   *Reality*: They are distinct tools. Training changes the brain; RAG adds a library. For adding new factual knowledge, RAG wins in 99% of cases. Fine-tuning teaches behavior and format, not facts.
2.  **"Fine-Tuning is for teaching new facts."**
    *   *Reality*: Fine-tuning is terrible at facts and excellent at style, formatting, and behavior. Trying to fine-tune a model to "know your company data" leads to highly confident hallucinations.
3.  **"Hallucination is a bug you can train away."**
    *   *Reality*: It is a fundamental property of next-token prediction. It must be addressed at the system level via RAG, grounding checks, and calibrated abstention.
4.  **"A decreasing loss curve guarantees capability."**
    *   *Reality*: Loss can drop due to memorization or test-set contamination. Without a clean, held-out, uncontaminated evaluation suite, you are only fooling yourself.
5.  **"Architecture dominates data."**
    *   *Reality*: A simple or mediocre architecture on clean, high-quality, deduplicated data will easily beat a state-of-the-art transformer trained on web slop.
6.  **"A 7B model can be trained on a 24GB consumer GPU."**
    *   *Reality*: Model weights occupy `7B × 2 = 14GB` (16-bit). However, training requires weights, gradients, optimizer states (e.g., AdamW), and activation memory. You need ~16–20 bytes per parameter, translating to ~100GB+ VRAM for a 7B model.
7.  **"Tokenizers are simple pre-processors that don't affect reasoning."**
    *   *Reality*: BPE tokenizers cause spelling issues, poor arithmetic behavior, and vulnerability to glitch tokens. Tokenization is often where the weirdest model behaviors begin.
8.  **"RLHF and DPO make the model smarter and more correct."**
    *   *Reality*: Preference alignment optimizes for what human raters prefer (e.g., agreeableness, formatting), which can lead to increased sycophancy and degraded calibration.
9.  **"Classical regularization intuition applies directly to LLMs."**
    *   *Reality*: Modern deep learning violates traditional overfitting rules through phenomena like *double descent* and *grokking*, where models generalize better with more epochs and parameters.
10. **"Public benchmark scores represent actual task utility."**
    *   *Reality*: Benchmarks are easily contaminated and overfitted. The only metric that matters is a custom, task-specific evaluation harness designed for your workflows.
11. **"Reasoning is just fast pattern-matching."**
    *   *Reality*: Current models interpolate memorized templates. Genuine multi-step logic requires separating retrieval and draft hypotheses from execution and verification.

---

## 3. The Master Curriculum

### Phase P0: Systems & GPU Foundations (Pre-requisite)
*   **Concepts**: Linux CLI, git, CUDA memory hierarchy, profiling kernel execution, identifying OOM/NaN roots, Docker, compute budget estimation.
*   **Goal**: Understand why training fails due to data loaders, GPU deadlocks, or out-of-memory errors before you write a model.

### Phase A: Deep Learning Mechanics & Math
*   **Concepts**: Matrix calculus, Jacobians, forward/backward passes, custom autograd engines, AdamW optimization, learning rate schedules (cosine annealing with warmup), numerical stability (log-sum-exp, Softmax overflow).
*   **Project**: Build a custom deep learning framework (like micrograd) with an autograd engine from scratch. Train it on MNIST using pure NumPy.
*   **Milestone**: Custom backward pass matches PyTorch autograd output within $10^{-7}$ precision.

### Phase B: Language Model Foundations
*   **Concepts**: Tokenization (BPE), Embeddings, Scaled Dot-Product Attention, Multi-Head Attention (MHA), vanilla encoder-decoder blocks, Positional Encodings.
*   **Project**: Write a BPE tokenizer from scratch and train a 10M–50M parameter autoregressive Transformer (nanoGPT-style) on a raw text corpus (e.g., Shakespeare).
*   **Milestone**: Model overfits the training set, validation loss declines predictably, and it generates coherent text.

### Phase C: Modern LLM Architecture (Llama-style)
*   **Concepts**: Rotary Position Embeddings (RoPE), RMSNorm, SwiGLU activations, Grouped-Query Attention (GQA), KV Caching, FlashAttention mathematical principles.
*   **Project**: Build a Llama-style decoder model block-by-block. Implement KV-caching.
*   **Milestone**: The model runs inference locally, with the KV-cache accelerating generation speed by at least 3× compared to standard autoregressive iteration.

### Phase D: AI Systems & Cognitive Engineering (Track A)
*   **Concepts**: Multi-agent orchestration, RAG pipelines, vector databases (Chroma/Milvus), document chunking strategies, planning engines (ReAct, Plan-and-Solve), reflection loops, shared blackboard workspaces.
*   **Project**: Construct Kattappa Core OS using existing models. Build the memory recall, reasoning, planning, and safety review nodes.
*   **Milestone**: A complete, functional cognitive graph that outperforms raw LLM prompts on complex multi-step OS workflows.

### Phase E: Post-Training & Alignment
*   **Concepts**: Supervised Fine-Tuning (SFT), Parameter-Efficient Fine-Tuning (LoRA, QLoRA), Direct Preference Optimization (DPO), RLHF, Constitutional AI, formatting via chat templates (ChatML).
*   **Project**: Apply LoRA SFT to a small open model (e.g., Qwen-1.5B) to teach it Kattappa's behavior, followed by DPO alignment.
*   **Milestone**: The model stops rambling and responds strictly within Kattappa's personality guidelines.

### Phase F: Pre-training at Scale
*   **Concepts**: Data deduplication (MinHash LSH), quality filtering pipelines, Mixed Precision training (FP16/BF16), Distributed Data Parallelism (DDP), Tensor Parallelism (TP), Pipeline Parallelism (PP), ZeRO Stages 1, 2, and 3.
*   **Project**: Launch a pre-training run for a 100M to 1B parameter model across a multi-GPU setup.
*   **Milestone**: Training run achieves Model Flops Utilization (MFU) $> 45\%$ without gradient explosions or NaNs.

---

## 4. Nine Critical Laptop/Colab Experiments

```
  Experiment 1 ──> Experiment 2 ──> Experiment 3 ──> Experiment 4 ──> Experiment 5
  (micrograd)      (Tokenizer)       (nanoGPT)        (RAG vs SFT)     (Kattappa OS)
                                                           │
  Experiment 9 <── Experiment 8 <── Experiment 7 <── Experiment 6 <┘
  (SFT & DPO)      (Llama-style)    (Eval Harness)   (Abstention)
```

### Experiment 1: Build micrograd
*   **Goal**: Understand backpropagation and gradient descent at the scalar level.
*   **Task**: Implement a scalar-value autograd engine with addition, multiplication, ReLU, and power operations. Construct a Multi-Layer Perceptron (MLP) and train it on a toy dataset.
*   **Verification**: Ensure gradient computations exactly match analytical calculations.

### Experiment 2: Build a BPE Tokenizer
*   **Goal**: Expose why LLMs struggle with character spelling and math.
*   **Task**: Implement Byte-Pair Encoding from scratch. Train it on a text file, then analyze token mappings for numbers, repeated letters, and non-English characters.
*   **Verification**: Watch arithmetic and spelling fail due to token splits (e.g., "12345" chunked into unpredictable sub-tokens).

### Experiment 3: Train nanoGPT
*   **Goal**: Build a small autoregressive language model.
*   **Task**: Build a decoder-only transformer (10M–50M parameters) using PyTorch. Train it on Shakespeare or TinyStories.
*   **Verification**: The model successfully learns the character/word patterns of the corpus and generates readable sequences.

### Experiment 4: RAG vs. Fine-Tuning
*   **Goal**: Permanently understand what fine-tuning does and does not do.
*   **Task**: Create a document containing fictional facts (e.g., *"Bala Sekhar created the Kattappa project in 2026"*). 
    *   Set up a prompting baseline.
    *   Set up a RAG pipeline retrieving from the document.
    *   Fine-tune a 1.5B model (via LoRA) on Q&A pairs of these facts.
*   **Verification**: Document that the fine-tuned model hallucinates details when queried on new configurations, whereas RAG answers accurately using the retrieved context.

### Experiment 5: Build Kattappa Core
*   **Goal**: Build a cognitive operating system.
*   **Task**: Build the LangGraph pipeline with observations, memory, planning, safety reviews, and verifications using frontier model APIs.
*   **Verification**: Execute multi-step commands and verify that the system handles errors and tool execution safely.

### Experiment 6: Grounding & Abstention
*   **Goal**: Control hallucinations.
*   **Task**: Add a Metacognitive Gate that evaluates whether the draft response is supported by the recalled context. If unsupported, force the system to state: *"I don't know."*
*   **Verification**: Queries that are not answered in memory result in clean abstention instead of confabulation.

### Experiment 7: Automated Eval Harness
*   **Goal**: Learn how to measure capability.
*   **Task**: Write an automated scoring script that tests your pipeline against 50 diverse user intents. Use a stronger model as an evaluator (LLM-as-a-Judge) with a strict rubric.
*   **Verification**: Measure how verbose or bloated answers game the scoring matrix, highlighting Goodhart's law.

### Experiment 8: Build a Llama-style Decoder
*   **Goal**: Transition to modern transformer design.
*   **Task**: Implement Rotary Position Embeddings (RoPE), RMSNorm, SwiGLU activation, and Grouped-Query Attention (GQA). Add a Key-Value (KV) cache for fast token generation.
*   **Verification**: Run benchmark speed tests to show the KV cache drastically reduces generation latency.

### Experiment 9: SFT & DPO Alignment
*   **Goal**: Align model behavior to human preference.
*   **Task**: Fine-tune a small model on formatting templates, then run a DPO alignment pass to restrict its tone to a helpful, concise assistant format.
*   **Verification**: Compare base vs. aligned model behavior on instructions.

---

## 5. Module 1: Neural Networks & Backpropagation

### A. Explain Like I'm 10 Years Old
Imagine you are training a robot to recognize a mango 🍋. You show the robot features:
*   **Color**: Yellow
*   **Shape**: Oval
*   **Taste**: Sweet

At first, the robot guesses randomly. It makes mistakes, guessing "lemon" or "banana". Every time it gets it wrong, you tell it, and it adjusts its internal rules. Eventually, it learns the perfect combination of Yellow + Oval + Sweet = Mango.

A **Neural Network** is just a giant machine that learns to find patterns by making guesses, calculating how wrong those guesses are, and adjusting its settings to make fewer mistakes next time.

### B. Biological Inspiration
Our brains contain billions of interconnected cells called **Neurons**. When you see something, electrical signals pass from neuron to neuron. If the signal is strong enough, the neuron "fires" and passes the signal to the next.
```
  [Biological Neuron]
  Dendrites (Inputs) ──> Cell Body (Summation) ──> Axon (Output) ──> Synapses (Weights)
  
  [Artificial Neuron]
  x_1 ──(w_1)──┐
  x_2 ──(w_2)──┼──> Sum (Σ x_i w_i + b) ──> Activation Function (f) ──> Output (y)
  x_3 ──(w_3)──┘
```
An **Artificial Neural Network** mimics this structure:
1.  **Input Layer**: Receives raw data (e.g., salary, experience).
2.  **Hidden Layers**: Process features and find intermediate patterns.
3.  **Output Layer**: Produces the final prediction (e.g., Hire vs. Don't Hire).

### C. Mathematical Explanation of a Neuron
A single neuron receives inputs ($x_1, x_2, \dots, x_n$).
Each input has a corresponding **Weight** ($w_1, w_2, \dots, w_n$) indicating its importance.
The neuron performs a weighted sum of the inputs and adds a constant offset called **Bias** ($b$):
$$z = \sum_{i=1}^{n} (x_i w_i) + b = x_1 w_1 + x_2 w_2 + \dots + x_n w_n + b$$

#### Example Calculation:
If inputs are $x_1 = 5, x_2 = 2$ and weights are $w_1 = 0.6, w_2 = 0.5$ with bias $b = 1.0$:
$$z = (5 \times 0.6) + (2 \times 0.5) + 1.0 = 3.0 + 1.0 + 1.0 = 5.0$$

#### Activation Function:
To make the network capable of learning non-linear, complex patterns (instead of simple linear formulas), we pass $z$ through an activation function:
1.  **Sigmoid**: Bounds output between 0 and 1 (useful for probabilities).
    $$\sigma(z) = \frac{1}{1 + e^{-z}}$$
2.  **ReLU (Rectified Linear Unit)**: Replaces negative values with zero (extremely popular in modern models).
    $$f(z) = \max(0, z)$$

### D. Production Usage
*   **Translation**: English sentence vectors are fed into a network to output Telugu word vectors.
*   **Autoregressive Models**: Feed preceding text tokens to predict the probability distribution of the next token.

---

## 6. Exercises & Mini-Project

### Exercise 1: Weighted Sum Calculation
Given the following variables:
*   Inputs: $x_1 = 3, x_2 = 4, x_3 = 1$
*   Weights: $w_1 = 0.2, w_2 = 0.5, w_3 = -1.0$
*   Bias: $b = 0.5$

Calculate the output $z$ before activation.

### Exercise 2: ReLU Activation
Calculate the output of the ReLU activation function for:
*   Input $z = -8.5$
*   Input $z = 4.2$

### Exercise 3: Core Concepts Matchup
Which statement is correct?
*   **A**: Transformers were invented to create Neural Networks.
*   **B**: Neural Networks are the foundation upon which Transformers are built.

---

### Mini-Project: The Hiring Predictor Blueprint
Draw a simple neural network that predicts whether to hire a software engineer based on three inputs:
1.  **Years of Experience**
2.  **Coding Test Score**
3.  **Interview Communication Rating**

Your network should have:
*   An **Input Layer** (3 nodes)
*   A **Hidden Layer** (4 nodes, using ReLU activation)
*   An **Output Layer** (1 node, using Sigmoid activation to represent the probability of hiring)

```
  [Input Layer]          [Hidden Layer]          [Output Layer]
  
  Experience ───────┬───> [ Neuron 1 ] ───┐
                    ├───> [ Neuron 2 ] ───┼───> [ Hiring Probability ]
  Coding Score ─────┼───> [ Neuron 3 ] ───┤       (0.0 to 1.0)
                    ├───> [ Neuron 4 ] ───┘
  Interview Score ──┘
```

#### Assignment:
Write a Python script that calculates the forward pass of this neuron using NumPy. Initialize weights randomly and compute the output for the input vector `[3 years experience, 85/100 coding score, 9/10 interview score]`.

---

## 7. The LLM Engineer's Verification Checklist
Before moving onto distributed training or scale, you must be able to explain:
- [ ] Why does fine-tuning fail to inject new factual knowledge reliably?
- [ ] What is the exact VRAM cost formula for AdamW optimizer states during training?
- [ ] How does Rotary Position Embedding (RoPE) represent token positions?
- [ ] Why did Grouped-Query Attention (GQA) replace Multi-Head Attention in modern architectures?
