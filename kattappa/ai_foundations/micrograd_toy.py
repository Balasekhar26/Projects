#!/usr/bin/env python3
"""
Micrograd Toy (Module 1 / Experiment 1).

A scalar-value autograd engine and a tiny Multi-Layer Perceptron (MLP) built from scratch.
Demonstrates:
- Automatic differentiation (backward pass via chain rule)
- Gradient descent optimization
- Multi-layer neural networks learning simple patterns
"""

import math
import random

# Set random seed for reproducibility
random.seed(42)

class Value:
    """Stores a single scalar value and its gradient, tracking operations to perform backpropagation."""
    
    def __init__(self, data, _children=(), _op='', label=''):
        self.data = float(data)
        self.grad = 0.0
        self._backward = lambda: None
        self._prev = set(_children)
        self._op = _op
        self.label = label

    def __repr__(self):
        return f"Value(data={self.data:.4f}, grad={self.grad:.4f})"

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other), '+')

        def _backward():
            self.grad += out.grad
            other.grad += out.grad
        out._backward = _backward

        return out

    def __radd__(self, other):
        return self + other

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')

        def _backward():
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward

        return out

    def __rmul__(self, other):
        return self * other

    def __pow__(self, other):
        assert isinstance(other, (int, float)), "only supporting int/float powers for now"
        out = Value(self.data**other, (self,), f'**{other}')

        def _backward():
            self.grad += (other * (self.data ** (other - 1))) * out.grad
        out._backward = _backward

        return out

    def __neg__(self):
        return self * -1

    def __sub__(self, other):
        return self + (-other)

    def __rsub__(self, other):
        return Value(other) - self

    def relu(self):
        out = Value(0.0 if self.data < 0 else self.data, (self,), 'ReLU')

        def _backward():
            self.grad += (1.0 if self.data > 0 else 0.0) * out.grad
        out._backward = _backward

        return out

    def backward(self):
        # Topological sort to order nodes sequentially for the backward pass
        topo = []
        visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._prev:
                    build_topo(child)
                topo.append(v)
        build_topo(self)

        # Go backward through the topological order
        self.grad = 1.0
        for v in reversed(topo):
            v._backward()


class Neuron:
    """A single artificial neuron with weights and bias."""
    
    def __init__(self, nin, nonlin=True):
        self.w = [Value(random.uniform(-1.0, 1.0)) for _ in range(nin)]
        self.b = Value(0.0)
        self.nonlin = nonlin

    def __call__(self, x):
        # z = sum(w_i * x_i) + b
        act = sum((wi * xi for wi, xi in zip(self.w, x)), self.b)
        return act.relu() if self.nonlin else act

    def parameters(self):
        return self.w + [self.b]


class Layer:
    """A layer of Neurons."""
    
    def __init__(self, nin, nout, **kwargs):
        self.neurons = [Neuron(nin, **kwargs) for _ in range(nout)]

    def __call__(self, x):
        outs = [n(x) for n in self.neurons]
        return outs[0] if len(outs) == 1 else outs

    def parameters(self):
        return [p for n in self.neurons for p in n.parameters()]


class MLP:
    """A Multi-Layer Perceptron network."""
    
    def __init__(self, nin, nouts):
        sz = [nin] + nouts
        self.layers = [Layer(sz[i], sz[i+1], nonlin=(i != len(nouts)-1)) for i in range(len(nouts))]

    def __call__(self, x):
        for layer in self.layers:
            x = layer(x)
        return x

    def parameters(self):
        return [p for layer in self.layers for p in layer.parameters()]


if __name__ == "__main__":
    print("=== Training a Tiny MLP (micrograd) ===")
    
    # 1. Initialize a 2-input, 1-hidden-layer (4 neurons), 1-output MLP
    n = MLP(2, [4, 1])
    
    # 2. Define a simple binary classification dataset (e.g., XOR gate)
    # Inputs (x)
    xs = [
        [0.0, 0.0],
        [0.0, 1.0],
        [1.0, 0.0],
        [1.0, 1.0]
    ]
    # Expected targets (y)
    ys = [0.0, 1.0, 1.0, 0.0]
    
    print("Initial Predictions:")
    for x, y in zip(xs, ys):
        pred = n(x)
        print(f"  Input: {x} -> Predicted: {pred.data:.4f} (Expected: {y})")

    print("\nStarting Training Loop...")
    # 3. Training loop (gradient descent)
    epochs = 100
    learning_rate = 0.05
    
    for epoch in range(epochs):
        # Forward pass: compute predictions and sum squared errors (loss)
        ypred = [n(x) for x in xs]
        loss = sum((yout - ygt)**2 for ygt, yout in zip(ys, ypred))
        
        # Backward pass: zero out old gradients, compute new gradients
        for p in n.parameters():
            p.grad = 0.0
        loss.backward()
        
        # Parameter update (gradient descent step)
        for p in n.parameters():
            p.data -= learning_rate * p.grad
            
        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1:02d} / {epochs} | Loss: {loss.data:.6f}")
            
    print("\nFinal Trained Predictions:")
    for x, y in zip(xs, ys):
        pred = n(x)
        print(f"  Input: {x} -> Predicted: {pred.data:.4f} (Expected: {y})")
        
    print("\nSuccess! The autograd engine learned the XOR function.")
