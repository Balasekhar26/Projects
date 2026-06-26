# Solutions — Module 1: Neural Networks Exercises

This document provides the verified step-by-step solutions to the exercises presented in [AI_FOUNDATIONS.md](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/AI_FOUNDATIONS.md).

---

## Exercise 1: Weighted Sum Calculation

### Problem
Given the following variables:
*   Inputs: $x_1 = 3, x_2 = 4, x_3 = 1$
*   Weights: $w_1 = 0.2, w_2 = 0.5, w_3 = -1.0$
*   Bias: $b = 0.5$

Calculate the output $z$ before activation.

### Solution
The formula for the pre-activation weighted sum $z$ is:
$$z = \sum_{i=1}^{3} (x_i w_i) + b = x_1 w_1 + x_2 w_2 + x_3 w_3 + b$$

Substituting the given values:
$$z = (3 \times 0.2) + (4 \times 0.5) + (1 \times -1.0) + 0.5$$
$$z = 0.6 + 2.0 - 1.0 + 0.5$$
$$z = 2.6 - 1.0 + 0.5$$
$$z = 1.6 + 0.5$$
$$z = 2.1$$

**Answer**: $z = 2.1$

---

## Exercise 2: ReLU Activation

### Problem
Calculate the output of the ReLU activation function for:
*   Input $z = -8.5$
*   Input $z = 4.2$

### Solution
The definition of the ReLU (Rectified Linear Unit) activation function is:
$$f(z) = \max(0, z)$$

1.  For $z = -8.5$:
    $$f(-8.5) = \max(0, -8.5) = 0.0$$
2.  For $z = 4.2$:
    $$f(4.2) = \max(0, 4.2) = 4.2$$

**Answer**:
*   For input $-8.5$, output is **$0.0$**
*   For input $4.2$, output is **$4.2$**

---

## Exercise 3: Core Concepts Matchup

### Problem
Which statement is correct?
*   **A**: Transformers were invented to create Neural Networks.
*   **B**: Neural Networks are the foundation upon which Transformers are built.

### Solution
**Statement B** is correct. 

*Explanation*: A Transformer is a specific deep learning architecture composed of neural network layers (specifically self-attention modules and feed-forward layers). Therefore, Neural Networks are the fundamental building blocks used to construct Transformers.

**Answer**: **B**
