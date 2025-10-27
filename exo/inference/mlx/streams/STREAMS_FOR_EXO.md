# MLX Streams for Exo - Critical for GIL-Free Operation

## Why Streams Matter for Exo

In the distributed inference engine, **streams are CRITICAL** for:

1. **Parallelizing distributed work** - Multiple nodes sending/receiving tensors
2. **Overlapping compute and network I/O** - Don't block on gRPC while GPU works
3. **Python 3.14 free-threading** - Multiple Python threads can dispatch MLX work concurrently
4. **Avoiding serialization bottlenecks** - Without streams, everything queues on default stream

## The Problem Without Streams

```python
# BAD: Everything serializes on default stream
result1 = await peer1.send_tensor(shard1, tensor1)  # GPU waits
result2 = await peer2.send_tensor(shard2, tensor2)  # GPU waits
result3 = await inference_engine.infer_tensor(...)  # GPU waits

# Network I/O blocks GPU work, GPU work blocks network I/O
```

## The Solution: Stream-Based Execution

```python
# GOOD: Independent work runs in parallel
import mlx.core as mx

# Create streams for different types of work
s_compute = mx.new_stream(mx.gpu)   # Inference compute
s_network = mx.new_stream(mx.gpu)   # Network tensor prep
s_cache = mx.new_stream(mx.gpu)     # KV cache updates

# All three can overlap!
with mx.stream(s_compute):
    logits = model(input_tokens, cache=cache)

with mx.stream(s_network):
    serialized = prepare_tensor_for_grpc(output)

with mx.stream(s_cache):
    cache.update(kv_state)

# Only synchronize when you actually need results
mx.synchronize(s_compute)  # Just wait for compute
result = logits
```

## Key Patterns for Exo

### 1. **Distributed Inference with Streams**

From your SVD kernel code - perfect pattern for exo:

```python
# Split work across multiple remote nodes using streams
dev = mx.default_device()
streams = [mx.new_stream(dev) for _ in range(num_peers)]

results = [None] * len(peers)
for idx, peer in enumerate(peers):
    st = streams[idx % len(streams)]
    with mx.stream(st):
        # Prepare tensor on this stream
        tensor_slice = input_tensor[:, slice_ranges[idx]]
        # Send to peer (gRPC serialization happens in parallel)
        results[idx] = await peer.send_tensor(shard, tensor_slice)

# Wait for all peers to finish
mx.synchronize()

# Combine results
combined = mx.concatenate(results, axis=1)
```

### 2. **Async Callbacks Without Blocking**

From `mlx_streams.py` - use for non-blocking token generation:

```python
from exo.inference.mlx.streams.mlx_streams import on_stream_complete_async

s_inference = mx.new_stream(mx.gpu)

async def on_token_ready():
    # Broadcast new token to all peers
    await node.broadcast_result(request_id, new_tokens, is_finished)

# Inference runs on GPU stream
with mx.stream(s_inference):
    next_logits = model.forward(tokens, cache)
    next_token = sample(next_logits)

# Callback fires when inference completes, doesn't block main loop
await on_stream_complete_async(s_inference, on_token_ready)
```

### 3. **Pipeline Pattern: Prefetch While Computing**

Critical for continuous token generation:

```python
# Stream 0: Current inference
# Stream 1: Prepare next batch
# Stream 2: Send results

s_current = mx.new_stream(mx.gpu)
s_next = mx.new_stream(mx.gpu)
s_send = mx.new_stream(mx.gpu)

while not finished:
    with mx.stream(s_current):
        logits = model(current_tokens, cache)
        next_token = sample(logits)

    with mx.stream(s_next):
        # Prepare next batch while current batch computes
        next_tokens = prepare_next_batch(next_token)

    with mx.stream(s_send):
        # Send results while computing next
        await broadcast_token(next_token)

    # Rotate streams for next iteration
    s_current, s_next = s_next, s_current
```

### 4. **ThreadPoolExecutor Integration for Free-Threading**

From Python 3.14 free-threading + MLX:

```python
from concurrent.futures import ThreadPoolExecutor
import asyncio

# Multiple Python threads can dispatch MLX work concurrently
executor = ThreadPoolExecutor(max_workers=4)  # No GIL!

# Each thread gets its own stream
def process_on_thread(thread_id, tensor_batch):
    stream = mx.new_stream(mx.gpu)
    with mx.stream(stream):
        result = model.forward(tensor_batch)
    mx.synchronize(stream)
    return result

# Fan-out to multiple threads
futures = []
for i, batch in enumerate(batches):
    future = executor.submit(process_on_thread, i, batch)
    futures.append(future)

# Fan-in results
results = [f.result() for f in futures]
```

## Exo-Specific Stream Strategy

### Recommended Stream Setup

```python
class MLXDynamicShardInferenceEngine(InferenceEngine):
    def __init__(self, shard_downloader: ShardDownloader):
        self.shard = None
        self.shard_downloader = shard_downloader

        # Stream strategy for distributed inference
        self.device = mx.default_device()

        # Separate streams for different work types
        self.streams = {
            'inference': mx.new_stream(self.device),    # Model forward pass
            'sampling': mx.new_stream(self.device),     # Token sampling
            'cache': mx.new_stream(self.device),        # KV cache updates
            'network_prep': mx.new_stream(self.device), # Tensor serialization
        }

        # For distributed work across multiple peers
        self.peer_streams = [
            mx.new_stream(self.device) for _ in range(4)
        ]
```

### Usage in infer_tensor

```python
async def infer_tensor(
    self,
    request_id: str,
    shard: Shard,
    input_data: MLXArray,
    inference_state: Optional[dict] = None
) -> tuple[MLXArray, Optional[dict]]:
    await self.ensure_shard(shard)
    state = await self.poll_state(request_id)

    # Use inference stream for model forward
    with mx.stream(self.streams['inference']):
        x = input_data.data
        output_data = self.model(x, **state, **(inference_state or {}))

    # Use cache stream for cache updates (can overlap with next infer)
    with mx.stream(self.streams['cache']):
        if 'cache' in state:
            state['cache'].update(...)

    # Only synchronize when we need results
    mx.synchronize(self.streams['inference'])

    return MLXArray(output_data), inference_state
```

### Usage in distributed forward

```python
async def forward_tensor(
    self,
    base_shard: Shard,
    tensor: MLXArray,
    request_id: str,
    target_index: int,
    inference_state: Optional[dict] = None,
) -> None:
    target_peer = self.get_peer_for_partition(target_index)

    # Use network prep stream
    with mx.stream(self.streams['network_prep']):
        # Serialize tensor for gRPC (happens in parallel with inference)
        serialized_data = tensor.tobytes()

    # Don't synchronize here - let it overlap
    # gRPC send will implicitly wait if needed
    await target_peer.send_tensor(shard, tensor, inference_state, request_id)
```

## Performance Guidelines

### DO:
✅ Create a small, fixed set of streams per device (2-8 streams)
✅ Use stream context managers for readability
✅ Synchronize at clear boundaries (before reading results, checkpoints)
✅ Let MLX track cross-stream dependencies automatically
✅ Batch related ops within a single stream

### DON'T:
❌ Create streams dynamically per operation
❌ Call `mx.synchronize()` after every op
❌ Let everything fall to default stream
❌ Mix streams haphazardly without scoped contexts
❌ Over-synchronize "just to be safe"

## Python 3.14 Free-Threading Benefits

With no GIL:
- Multiple Python threads can dispatch MLX ops **in parallel**
- Each thread can use its own stream → true parallelism
- ThreadPoolExecutor becomes actually useful for MLX work
- Async/await + streams = maximum throughput

## Critical Files

1. **`mlx_streams.py`** - Helper utilities:
   - `on_stream_complete()` - Background wait + callback
   - `on_stream_complete_async()` - Async variant
   - `after_eval()` - Wait for array evaluation

2. **`Streams-Guide.md`** - Comprehensive patterns and anti-patterns

3. **`DEVICES_STREAMS.md`** - Core MLX streams API reference

## References

See the curated docs in this directory for:
- Banded execution patterns
- Multi-stream overlap examples
- Async integration patterns
- Common pitfalls and solutions

## Next Steps for Exo

1. ✅ MLXArray wrapper created (already GIL-free ready)
2. ⏭️ Add stream management to MLXDynamicShardInferenceEngine
3. ⏭️ Use streams in distributed tensor forwarding
4. ⏭️ Add async callbacks for token generation
5. ⏭️ Benchmark with Python 3.14 free-threaded mode
