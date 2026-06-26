#!/usr/bin/env python3
"""
Hiring Predictor Mini-Project (Module 1).

Calculates the forward pass of a 3-input, 4-hidden-neuron, 1-output neural network.
- Input: [Years of Experience, Coding Test Score, Interview Rating]
- Hidden Layer: ReLU activation
- Output Layer: Sigmoid activation (representing probability of hire)
"""

import numpy as np

# Set random seed for reproducibility
np.random.seed(42)

def relu(x):
    """Rectified Linear Unit activation function."""
    return np.maximum(0, x)

def sigmoid(x):
    """Sigmoid activation function."""
    return 1 / (1 + np.exp(-x))

def run_forward_pass(experience, coding_score, interview_rating):
    # 1. Define Input Vector (x)
    # Experience (0-15 years), Coding Score (0-100), Interview (0-10)
    x = np.array([experience, coding_score, interview_rating])
    print(f"=== Forward Pass Inputs ===")
    print(f"Experience: {x[0]} years")
    print(f"Coding Score: {x[1]}/100")
    print(f"Interview Rating: {x[2]}/10")
    print(f"Input Vector Shape: {x.shape}\n")

    # 2. Hidden Layer Parameters
    # Input dimension: 3, Hidden dimension: 4
    # Weights W1 shape: (3, 4)
    # Bias b1 shape: (4,)
    W1 = np.random.uniform(-1.0, 1.0, (3, 4))
    b1 = np.random.uniform(-0.5, 0.5, 4)
    print(f"=== Hidden Layer Parameters ===")
    print(f"W1 weights:\n{W1}")
    print(f"b1 biases: {b1}\n")

    # 3. Output Layer Parameters
    # Input dimension: 4, Output dimension: 1
    # Weights W2 shape: (4, 1)
    # Bias b2 shape: (1,)
    W2 = np.random.uniform(-1.0, 1.0, (4, 1))
    b2 = np.random.uniform(-0.5, 0.5, 1)
    print(f"=== Output Layer Parameters ===")
    print(f"W2 weights:\n{W2}")
    print(f"b2 bias: {b2}\n")

    # 4. Forward Pass Calculation
    # Step A: Linear activation of hidden layer
    z1 = np.dot(x, W1) + b1
    print(f"z1 (pre-activation sum for hidden layer): {z1}")

    # Step B: Apply non-linear ReLU activation
    h = relu(z1)
    print(f"h (hidden layer ReLU activation): {h}\n")

    # Step C: Linear activation of output layer
    z2 = np.dot(h, W2) + b2
    print(f"z2 (pre-activation sum for output layer): {z2}")

    # Step D: Apply non-linear Sigmoid activation
    y = sigmoid(z2)
    print(f"y (output layer hiring probability): {y[0]:.4f}")
    
    decision = "HIRE" if y[0] >= 0.5 else "DO NOT HIRE"
    print(f"Decision Boundary: {decision} (Threshold: 0.5)\n")
    return y[0]

if __name__ == "__main__":
    # Input vector: [3 years experience, 85/100 coding score, 9/10 interview score]
    run_forward_pass(3.0, 85.0, 9.0)
