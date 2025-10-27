# Metal Kernel References for Exo MLX

This directory contains reference implementations of custom Metal kernels and MLX kernel wrappers from various projects. These serve as examples for implementing high-performance, threadgroup-optimized kernels for the GIL-free exo inference engine.

## Directory Structure

### `xlstm/` - xLSTM Metal Kernels
High-performance mLSTM (matrix LSTM) kernels with advanced threadgroup usage.

**Metal Kernels:**
- `mlstm_kernels.metal` - Core mLSTM kernels with threadgroup memory optimizations

**Python Wrappers:**
- `fw_kernel_parallel.py` - Forward pass parallel kernel
- `fw_kernel_recurrent.py` - Forward pass recurrent kernel
- `bw_kernel_parallel_dQ.py` - Backward pass: gradient w.r.t. queries
- `bw_kernel_parallel_dK.py` - Backward pass: gradient w.r.t. keys
- `bw_kernel_parallel_dV.py` - Backward pass: gradient w.r.t. values
- `bw_kernel_recurrent.py` - Backward pass recurrent kernel
- `bw_kernel_recurrent_wrapper.py` - Wrapper for recurrent backward kernels

**Key Features:**
- Threadgroup synchronization for parallel operations
- Memory coalescing patterns
- SIMD group operations
- Mixed precision (FP16/FP32) support

### `mlx_fast_kernels/` - Fast Custom Kernels
Optimized kernels for various linear algebra operations.

**Files:**
- `gemm_kernels.py` - General matrix multiplication kernels
- `qr_kernels.py` - QR decomposition kernels
- `ivf_kernels.py` - Inverted file index kernels (for similarity search)
- `shaders.py` - Utility shader functions

**Key Features:**
- Custom dispatch configurations
- Threadgroup tile sizes optimized for Apple Silicon
- Fast math operations

### `ember_ml/` - Linear Algebra Operations
Comprehensive linear algebra kernel implementations.

**Files:**
- `qr_ops.py` - QR decomposition
- `svd_ops.py` - Singular value decomposition
- `cholesky_ops.py` - Cholesky decomposition
- `eigen_ops.py` - Eigenvalue/eigenvector computations
- `orthogonal_ops.py` - Orthogonalization operations
- `matrix_ops.py` - General matrix operations
- `solvers_ops.py` - Linear system solvers
- `hpc16x8_ops.py` - High-performance computing with 16x8 tiles

**Key Features:**
- Blocked/tiled algorithms
- Numerical stability techniques
- Adaptive precision

### `misc/` - Miscellaneous Kernels
Additional reference implementations.

**Files:**
- `enhanced_tiled_hpc_qr.metal` - Tiled QR decomposition Metal kernel

## Usage Patterns

### 1. Basic MLX Kernel Definition
```python
from mlx import core as mx
from mlx.core import fast

# Define Metal kernel source
kernel_source = """
kernel void my_kernel(
    device const float* input [[buffer(0)]],
    device float* output [[buffer(1)]],
    uint gid [[thread_position_in_grid]]
) {
    output[gid] = input[gid] * 2.0f;
}
"""

# Compile and use
kernel = fast.metal_kernel(
    name="my_kernel",
    input_names=["input"],
    output_names=["output"],
    source=kernel_source
)
```

### 2. Threadgroup Memory Usage
From `mlstm_kernels.metal`:
```metal
kernel void mlstm_forward(
    ...
    threadgroup float* shared_mem [[threadgroup(0)]],
    uint tid [[thread_position_in_threadgroup]],
    uint tgid [[threadgroup_position_in_grid]]
) {
    // Use shared memory for cooperation
    threadgroup_barrier(mem_flags::mem_threadgroup);
    // ...
}
```

### 3. Grid/Threadgroup Configuration
```python
# From xLSTM kernels
grid_size = (batch_size, seq_len, 1)
threadgroup_size = (32, 1, 1)  # Warp size on Apple Silicon

output = kernel(
    inputs=[input_array],
    grid=grid_size,
    threadgroup=threadgroup_size
)
```

## Key Optimization Techniques

1. **Memory Coalescing**: Ensure adjacent threads access adjacent memory
2. **Threadgroup Barriers**: Synchronize threads for shared memory operations
3. **SIMD Operations**: Use SIMD group functions for warp-level primitives
4. **Occupancy**: Balance threadgroup size vs register/memory usage
5. **Fast Math**: Enable fast math for non-critical operations

## Python 3.14 Free-Threading Considerations

- MLX operations already release the GIL internally
- Kernel dispatch can happen from multiple Python threads
- Thread-safe kernel compilation and caching
- Async kernel execution with proper synchronization

## References

- Apple Metal Shading Language Specification
- MLX Documentation: https://ml-explore.github.io/mlx/
- Metal Performance Shaders Best Practices
