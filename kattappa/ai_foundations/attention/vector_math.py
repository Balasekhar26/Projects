import numpy as np

def matmul(A, B):
    """
    Computes matrix multiplication of A and B.
    Supports 2D matrix multiplication and 3D batched matrix multiplication.
    """
    return np.matmul(A, B)

def softmax(x, axis=-1):
    """
    Computes the Softmax activation function.
    Subtracts the maximum value for numerical stability (prevents overflow).
    """
    # Keepdims=True ensures shapes align for broadcasting
    max_x = np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x - max_x)
    sum_exp_x = np.sum(exp_x, axis=axis, keepdims=True)
    return exp_x / sum_exp_x

def layernorm(x, gamma, beta, eps=1e-5):
    """
    Computes Layer Normalization along the last dimension.
    LN(x) = ((x - mean) / sqrt(var + eps)) * gamma + beta
    """
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    x_norm = (x - mean) / np.sqrt(var + eps)
    return x_norm * gamma + beta
