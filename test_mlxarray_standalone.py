#!/usr/bin/env python
"""
Standalone test for MLXArray wrapper - no exo deps needed
"""

import sys
sys.path.insert(0, '/Volumes/stuff/exo-mlx')

import mlx.core as mx

# Import just the MLXArray module
from exo.inference.mlx_array import MLXArray, ensure_mlx_array, array_from_bytes

def test_basic():
    print("🧪 Testing basic MLXArray operations...\n")

    # Test 1: Create from list
    print("1. Creating MLXArray from list...")
    arr = MLXArray([1.0, 2.0, 3.0, 4.0])
    print(f"   Shape: {arr.shape}, dtype: {arr.dtype}")
    assert arr.shape == (4,)
    print("   ✅ PASS\n")

    # Test 2: Create from MLX array
    print("2. Creating MLXArray from MLX array...")
    mx_arr = mx.array([[1, 2], [3, 4]])
    arr2 = MLXArray(mx_arr)
    print(f"   Shape: {arr2.shape}, dtype: {arr2.dtype}")
    assert arr2.shape == (2, 2)
    print("   ✅ PASS\n")

    # Test 3: Serialization (CRITICAL for gRPC)
    print("3. Testing serialization/deserialization...")
    original = MLXArray([[1.5, 2.5, 3.5], [4.5, 5.5, 6.5]])
    print(f"   Original: shape={original.shape}, dtype={original.dtype}")

    # Serialize
    serialized = original.tobytes()
    print(f"   Serialized to {len(serialized)} bytes")

    # Deserialize
    reconstructed = array_from_bytes(
        serialized,
        shape=original.shape,
        dtype=str(original.dtype)
    )
    print(f"   Reconstructed: shape={reconstructed.shape}, dtype={reconstructed.dtype}")

    # Verify
    orig_mx = mx.array(original.data)
    recon_mx = mx.array(reconstructed.data)
    mx.eval(orig_mx, recon_mx)
    diff = mx.max(mx.abs(orig_mx - recon_mx))
    mx.eval(diff)

    print(f"   Max difference: {diff.item()}")
    assert diff.item() < 1e-6
    print("   ✅ PASS\n")

    # Test 4: Large tensor (like real model activations)
    print("4. Testing large tensor (batch=2, seq=128, hidden=512)...")
    import time
    shape = (2, 128, 512)
    large = MLXArray(mx.random.normal(shape))

    start = time.perf_counter()
    serialized_large = large.tobytes()
    ser_time = time.perf_counter() - start

    start = time.perf_counter()
    reconstructed_large = array_from_bytes(serialized_large, shape, str(large.dtype))
    deser_time = time.perf_counter() - start

    print(f"   Serialized {len(serialized_large)/1024/1024:.2f} MB in {ser_time*1000:.2f}ms")
    print(f"   Deserialized in {deser_time*1000:.2f}ms")
    assert reconstructed_large.shape == large.shape
    print("   ✅ PASS\n")

    # Test 5: Reshape
    print("5. Testing reshape...")
    arr = MLXArray([1, 2, 3, 4, 5, 6])
    reshaped = arr.reshape(2, 3)
    print(f"   Original: {arr.shape} -> Reshaped: {reshaped.shape}")
    assert reshaped.shape == (2, 3)
    print("   ✅ PASS\n")

    # Test 6: Indexing
    print("6. Testing indexing...")
    arr = MLXArray([[1, 2, 3], [4, 5, 6]])
    sliced = arr[0, :]
    print(f"   Original: {arr.shape} -> Sliced [0,:]: {sliced.shape}")
    assert sliced.shape == (3,)
    print("   ✅ PASS\n")

    # Test 7: ensure_mlx_array helper
    print("7. Testing ensure_mlx_array helper...")
    mlx_arr = MLXArray([1, 2, 3])
    result = ensure_mlx_array(mlx_arr)
    assert isinstance(result, MLXArray)
    print("   ✅ PASS\n")

    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nMLXArray is ready for GIL-free distributed inference!")

if __name__ == "__main__":
    try:
        test_basic()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
