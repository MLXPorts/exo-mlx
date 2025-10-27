#!/usr/bin/env python
"""
Test suite for NumPy → MLX migration in exo
Tests MLXArray wrapper and core inference operations
"""

import sys
import mlx.core as mx
from exo.inference.mlx_array import MLXArray, ensure_mlx_array, array_from_bytes

def test_mlx_array_creation():
    """Test MLXArray creation from various sources"""
    print("🧪 Testing MLXArray creation...")

    # From list
    arr1 = MLXArray([1.0, 2.0, 3.0, 4.0])
    assert arr1.shape == (4,), f"Expected shape (4,), got {arr1.shape}"
    print("  ✅ Created from list")

    # From MLX array
    mx_arr = mx.array([5.0, 6.0, 7.0, 8.0])
    arr2 = MLXArray(mx_arr)
    assert arr2.shape == (4,), f"Expected shape (4,), got {arr2.shape}"
    print("  ✅ Created from MLX array")

    # From nested list (array-like)
    nested = [[1.0, 2.0], [3.0, 4.0]]
    arr3 = MLXArray(nested)
    assert arr3.shape == (2, 2), f"Expected shape (2, 2), got {arr3.shape}"
    print("  ✅ Created from nested list")

    print("✅ MLXArray creation tests passed\n")

def test_mlx_array_serialization():
    """Test serialization/deserialization (critical for gRPC)"""
    print("🧪 Testing MLXArray serialization...")

    # Create test array
    original = MLXArray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    print(f"  Original shape: {original.shape}, dtype: {original.dtype}")

    # Serialize
    serialized = original.tobytes()
    print(f"  Serialized to {len(serialized)} bytes")

    # Deserialize
    reconstructed = array_from_bytes(
        serialized,
        shape=original.shape,
        dtype=str(original.dtype)
    )
    print(f"  Reconstructed shape: {reconstructed.shape}, dtype: {reconstructed.dtype}")

    # Verify shapes match
    assert reconstructed.shape == original.shape, \
        f"Shape mismatch: {reconstructed.shape} != {original.shape}"

    # Verify data matches
    orig_data = mx.array(original.data)
    recon_data = mx.array(reconstructed.data)
    mx.eval(orig_data, recon_data)

    diff = mx.max(mx.abs(orig_data - recon_data))
    mx.eval(diff)
    print(f"  Max difference: {diff.item()}")

    assert diff.item() < 1e-6, f"Data mismatch: max diff = {diff.item()}"

    print("✅ Serialization tests passed\n")

def test_mlx_array_operations():
    """Test basic MLX operations through wrapper"""
    print("🧪 Testing MLXArray operations...")

    arr = MLXArray([1.0, 2.0, 3.0, 4.0])

    # Test reshape
    reshaped = arr.reshape(2, 2)
    assert reshaped.shape == (2, 2), f"Expected (2,2), got {reshaped.shape}"
    print("  ✅ Reshape works")

    # Test indexing
    sliced = arr[1:3]
    assert sliced.shape == (2,), f"Expected (2,), got {sliced.shape}"
    print("  ✅ Indexing works")

    # Test item() for scalars
    scalar_arr = MLXArray([42.0])
    scalar_val = scalar_arr.item()
    assert abs(scalar_val - 42.0) < 1e-6, f"Expected 42.0, got {scalar_val}"
    print("  ✅ Scalar extraction works")

    print("✅ Operation tests passed\n")

def test_ensure_mlx_array():
    """Test the ensure_mlx_array helper"""
    print("🧪 Testing ensure_mlx_array helper...")

    # Already an MLXArray
    arr1 = MLXArray([1, 2, 3])
    result1 = ensure_mlx_array(arr1)
    assert isinstance(result1, MLXArray)
    print("  ✅ Passthrough for MLXArray")

    # Raw MLX array
    arr2 = mx.array([4, 5, 6])
    result2 = ensure_mlx_array(arr2)
    assert isinstance(result2, MLXArray)
    print("  ✅ Wraps raw MLX array")

    # List
    arr3 = [7, 8, 9]
    result3 = ensure_mlx_array(arr3)
    assert isinstance(result3, MLXArray)
    print("  ✅ Wraps list")

    print("✅ Helper function tests passed\n")

def test_large_tensor_serialization():
    """Test serialization of large tensors (like model activations)"""
    print("🧪 Testing large tensor serialization...")

    # Simulate a model activation: batch=2, seq_len=128, hidden=512
    shape = (2, 128, 512)
    large_arr = MLXArray(mx.random.normal(shape))
    print(f"  Created tensor with shape {shape}")

    # Serialize
    import time
    start = time.perf_counter()
    serialized = large_arr.tobytes()
    serialize_time = time.perf_counter() - start
    print(f"  Serialized {len(serialized) / 1024 / 1024:.2f} MB in {serialize_time*1000:.2f}ms")

    # Deserialize
    start = time.perf_counter()
    reconstructed = array_from_bytes(serialized, shape, str(large_arr.dtype))
    deserialize_time = time.perf_counter() - start
    print(f"  Deserialized in {deserialize_time*1000:.2f}ms")

    # Verify
    assert reconstructed.shape == large_arr.shape
    print("  ✅ Shape preserved")

    print("✅ Large tensor tests passed\n")

def test_mlx_available():
    """Verify MLX is available and working"""
    print("🧪 Testing MLX availability...")

    try:
        import mlx.core as mx
        print(f"  ✅ MLX version: {mx.__version__ if hasattr(mx, '__version__') else 'unknown'}")

        # Check default device
        device = mx.default_device()
        print(f"  ✅ Default device: {device}")

        # Try a simple operation
        a = mx.array([1, 2, 3])
        b = mx.array([4, 5, 6])
        c = a + b
        mx.eval(c)
        print(f"  ✅ Basic ops work: {list(c)}")

    except Exception as e:
        print(f"  ❌ MLX not available or broken: {e}")
        return False

    print("✅ MLX availability tests passed\n")
    return True

def run_all_tests():
    """Run complete test suite"""
    print("=" * 60)
    print("🚀 MLX Migration Test Suite")
    print("=" * 60)
    print()

    tests = [
        ("MLX Availability", test_mlx_available),
        ("MLXArray Creation", test_mlx_array_creation),
        ("MLXArray Serialization", test_mlx_array_serialization),
        ("MLXArray Operations", test_mlx_array_operations),
        ("ensure_mlx_array Helper", test_ensure_mlx_array),
        ("Large Tensor Serialization", test_large_tensor_serialization),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"❌ Test '{name}' failed with exception:")
            print(f"   {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            print()

    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
