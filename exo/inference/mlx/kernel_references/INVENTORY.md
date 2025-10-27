# Kernel Reference Inventory

## Summary
Collected **33 files** containing custom Metal kernel implementations and MLX wrappers.

## Contents

### Metal Kernels (2 files)
1. **xlstm/mlstm_kernels.metal** - mLSTM kernels with:
   - Soft-cap activation kernel
   - mLSTM step kernel with matrix memory updates
   - Gate-based operations (input/forget/output gates)
   - Outer product computations (k ⊗ v)

2. **misc/enhanced_tiled_hpc_qr.metal** - QR decomposition:
   - Tiled/blocked QR algorithm
   - High-performance computing patterns
   - Threadgroup synchronization

### Python Kernel Wrappers (31 files)

#### xLSTM Kernels (14 files)
Forward/backward mLSTM kernels with parallel and recurrent modes:
- Forward: `fw_kernel_parallel.py`, `fw_kernel_recurrent.py`
- Backward gradients: `bw_kernel_parallel_dQ.py`, `bw_kernel_parallel_dK.py`, `bw_kernel_parallel_dV.py`
- Recurrent backward: `bw_kernel_recurrent.py`, `bw_kernel_recurrent_wrapper.py`

#### Fast Kernels (6 files)
High-performance linear algebra:
- `gemm_kernels.py` - Tiled GEMM with 2D threadgroup memory
- `qr_kernels.py` - QR decomposition
- `ivf_kernels.py` - Inverted file index (similarity search)
- `shaders.py` - Utility shaders

#### Ember ML Kernels (12 files)
Comprehensive linear algebra suite:
- Decompositions: QR, SVD, Cholesky, Eigen
- Operations: Matrix ops, orthogonalization, inverses
- Solvers: Linear system solvers
- HPC variants: 16x8 tiled operations

## Key Patterns Identified

### 1. **MLX Kernel Definition Pattern**
```python
import mlx.core as mx

kernel_source = "#include <metal_stdlib>..."
kernel = mx.fast.metal_kernel(
    name="kernel_name",
    input_names=["in1", "in2"],
    output_names=["out"],
    source=kernel_source,
    header="#include <metal_stdlib>\nusing namespace metal;\n"
)
```

### 2. **Threadgroup Memory Usage**
```metal
kernel void my_kernel(
    device float* input [[buffer(0)]],
    device float* output [[buffer(1)]],
    threadgroup float* shared [[threadgroup(0)]],
    uint tid [[thread_position_in_threadgroup]],
    uint gid [[threadgroup_position_in_grid]]
) {
    // Load to shared memory
    shared[tid] = input[gid * THREADS + tid];
    threadgroup_barrier(mem_flags::mem_threadgroup);

    // Compute using shared data
    float sum = 0.0f;
    for (uint i = 0; i < THREADS; i++) {
        sum += shared[i];
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);

    output[gid * THREADS + tid] = sum;
}
```

### 3. **Grid Configuration**
From `gemm_kernels.py`:
- Grid size = total threads needed
- Threadgroup size = tile size (e.g., 32x8, 16x16)
- Uses `threadgroup_position_in_grid` to enumerate tiles
- Uses `thread_position_in_threadgroup` for intra-tile indexing

### 4. **Device-Aware Tuning**
```python
import mlx.core.metal as metal

def get_device_config():
    info = metal.device_info()
    exec_width = info.get("threadExecutionWidth", 32)
    device_name = info.get("device_name", "")

    # Choose tile sizes based on device
    if "M4" in device_name:
        tile_size = (32, 8)
    elif "M3" in device_name:
        tile_size = (16, 16)
    else:
        tile_size = (16, 8)

    return tile_size
```

### 5. **Shape Passing Pattern**
Instead of hardcoding shapes (which triggers recompiles):
```python
# Pass shapes via buffer
shape_array = mx.array([m, n, k], dtype=mx.uint32)
output = kernel(
    inputs=[A, B, shape_array],
    ...
)
```

### 6. **Barrier Synchronization**
Two barriers per iteration in tiled GEMM:
```metal
// Load tiles cooperatively
shared_A[tid] = A[...];
shared_B[tid] = B[...];
threadgroup_barrier(mem_flags::mem_threadgroup);  // After loads

// Accumulate
for (uint i = 0; i < TILE_K; i++) {
    sum += shared_A[...] * shared_B[...];
}
threadgroup_barrier(mem_flags::mem_threadgroup);  // After accumulation
```

## Optimization Techniques Observed

1. **Memory Coalescing** - Adjacent threads access adjacent memory locations
2. **Threadgroup Tiles** - 2D tiling in shared memory (e.g., 32x8, 16x16)
3. **Bank Conflict Avoidance** - Padding shared memory by +1 column
4. **SIMD-Aligned Tiles** - Tile sizes aligned to threadExecutionWidth
5. **Fast Math** - Using `fast::` Metal functions where precision allows
6. **Mixed Precision** - FP16 for memory, FP32 for accumulation
7. **Grid-Stride Loops** - For handling partial tiles and irregular sizes

## Next Steps for Exo Integration

1. **Identify Hot Paths** in exo inference:
   - Token sampling (softmax + argmax)
   - KV cache updates
   - Tensor serialization/deserialization for gRPC

2. **Create Custom Kernels**:
   - Fused sampling kernel (logsumexp + softmax + categorical)
   - Optimized tensor pack/unpack for network transfer
   - KV cache management with threadgroup coordination

3. **Thread-Safety Layer**:
   - Kernel compilation cache with locks
   - MLX stream management for multi-threading
   - Proper barrier usage for free-threaded Python

## References
- xLSTM kernels: Advanced recurrent patterns
- Ember ML: Numerical stability techniques
- Fast kernels: Production-quality GEMM patterns
