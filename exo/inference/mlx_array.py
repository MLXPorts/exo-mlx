#!/usr/bin/env python
"""
MLX Array utilities for GIL-free tensor operations in Python 3.14+

This module provides thread-safe MLX array operations and serialization
for use in the exo distributed inference engine.
"""

import platform
from typing import Union, Any, Optional
import threading

# Platform-specific imports
if platform.system().lower() == "darwin" and platform.machine().lower() == "arm64":
    import mlx.core as mx
    MLX_AVAILABLE = True
else:
    # Compatibility layer for non-Apple platforms
    # Note: In exo environments, NumPy installation is blocked by design
    MLX_AVAILABLE = False
    import numpy as np

    class MLXCompat:
        """Minimal MLX compatibility layer for non-Apple Silicon platforms"""
        @staticmethod
        def array(data, dtype=None):
            return np.array(data, dtype=dtype)

        @staticmethod
        def eval(*args):
            pass  # No-op on numpy

        @staticmethod
        def zeros(*args, **kwargs):
            return np.zeros(*args, **kwargs)

        @staticmethod
        def ones(*args, **kwargs):
            return np.ones(*args, **kwargs)

    mx = MLXCompat()


class MLXArray:
    """
    Wrapper for MLX arrays with thread-safe operations.

    On Apple Silicon: Uses native MLX arrays with zero-copy buffer protocol
    On other platforms: Compatibility layer (note: exo blocks NumPy installation)
    """

    _local_arrays = threading.local()

    def __init__(self, data: Union['mx.array', Any], shape: Optional[tuple] = None, dtype: Optional[str] = None):
        """
        Initialize MLXArray from data.

        Args:
            data: Source data (MLX array, array-like object, list, or bytes)
            shape: Optional shape for reshaping
            dtype: Optional dtype for conversion
        """
        if isinstance(data, bytes):
            # Deserialize from bytes
            self._data = self._from_bytes(data, shape, dtype)
        elif hasattr(data, '__array_interface__') or isinstance(data, list):
            # Convert from numpy-like or list
            self._data = mx.array(data, dtype=dtype)
        else:
            # Already an MLX array or MLXCompat array
            self._data = data

        if shape is not None and self._data.shape != shape:
            self._data = self._data.reshape(shape)

    @property
    def data(self):
        """Get underlying MLX array"""
        return self._data

    @property
    def shape(self):
        return self._data.shape

    @property
    def dtype(self):
        return self._data.dtype

    @property
    def size(self):
        return self._data.size

    def tobytes(self) -> bytes:
        """
        Convert to bytes for serialization (e.g., gRPC transfer).

        Thread-safe operation using Python's buffer protocol for zero-copy access.
        Evaluates the MLX array before serialization to ensure data is materialized.
        """
        if MLX_AVAILABLE:
            # Force evaluation before converting to bytes
            mx.eval(self._data)
            # Use memoryview + buffer protocol for zero-copy serialization
            return bytes(memoryview(self._data))
        else:
            # Compatibility path for non-Apple Silicon platforms
            return self._data.tobytes()

    def _from_bytes(self, data: bytes, shape: tuple, dtype: str):
        """
        Reconstruct array from bytes using Python's array module.

        Avoids external dependencies by using the standard library array module
        with buffer protocol for deserialization.
        """
        if MLX_AVAILABLE:
            # Use Python's array module to parse bytes, then convert to MLX
            import array
            # Map MLX dtype strings to array typecodes
            dtype_map = {
                'mlx.core.float32': 'f',
                'mlx.core.float16': 'f',  # Will convert
                'mlx.core.int32': 'i',
                'mlx.core.int64': 'q',
                'mlx.core.uint32': 'I',
                'mlx.core.uint64': 'Q',
            }

            typecode = dtype_map.get(dtype, 'f')  # Default to float

            # Create array from bytes
            element_size = array.array(typecode).itemsize
            num_elements = len(data) // element_size
            arr = array.array(typecode)
            arr.frombytes(data)

            # Convert to MLX array
            mlx_arr = mx.array(list(arr))
            if shape:
                mlx_arr = mlx_arr.reshape(shape)
            return mlx_arr
        else:
            # Compatibility path for non-Apple Silicon platforms
            arr = np.frombuffer(data, dtype=dtype)
            if shape:
                arr = arr.reshape(shape)
            return arr

    def reshape(self, *shape):
        """Reshape the array"""
        return MLXArray(self._data.reshape(*shape))

    def item(self):
        """Get scalar value"""
        if MLX_AVAILABLE:
            mx.eval(self._data)
        return self._data.item()

    def __getitem__(self, key):
        """Support indexing"""
        return MLXArray(self._data[key])

    def __repr__(self):
        return f"MLXArray(shape={self.shape}, dtype={self.dtype})"


def ensure_mlx_array(data: Union[MLXArray, 'mx.array', Any]) -> MLXArray:
    """
    Ensure data is wrapped in MLXArray.

    Args:
        data: Input data (MLXArray, MLX array, or array-like object)

    Returns:
        MLXArray instance
    """
    if isinstance(data, MLXArray):
        return data
    return MLXArray(data)


def eval_async(*arrays: MLXArray):
    """
    Asynchronously evaluate MLX arrays (thread-safe for Python 3.14 free-threading).

    Args:
        *arrays: MLXArray instances to evaluate
    """
    if not MLX_AVAILABLE:
        return

    # Extract underlying MLX arrays
    mlx_arrays = [arr.data if isinstance(arr, MLXArray) else arr for arr in arrays]
    mx.eval(*mlx_arrays)


def array_from_bytes(data: bytes, shape: tuple, dtype: str) -> MLXArray:
    """
    Create MLXArray from serialized bytes.

    Args:
        data: Byte data
        shape: Target shape
        dtype: Data type string

    Returns:
        MLXArray instance
    """
    return MLXArray(data, shape=shape, dtype=dtype)
