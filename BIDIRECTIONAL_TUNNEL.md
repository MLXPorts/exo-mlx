# Bidirectional SSH Tunnel Setup

## Complete Architecture

```
Mac #1 (192.168.2.2)                    Mac #2 (192.168.2.1)
    [Remote]                                [Local - THIS MACHINE]

    Exo Node                                Exo Node
    Port: 50060                             Port: 50051

    ┌─────────────────┐                     ┌─────────────────┐
    │  localhost:50052│◄────Tunnel──────────┤  localhost:50051│
    └─────────────────┘    -L Forward       └─────────────────┘

    ┌─────────────────┐                     ┌─────────────────┐
    │  localhost:50060│─────Tunnel─────────►│  localhost:50060│
    └─────────────────┘    -R Reverse       └─────────────────┘
```

## The Complete SSH Tunnel Command (Run on Mac #1)

```bash
ssh -L 50052:localhost:50051 -R 50060:localhost:50060 -N remoteuser@192.168.2.1
```

**What this does:**
- **`-L 50052:localhost:50051`**: Forward Mac #1's localhost:50052 → Mac #2's localhost:50051
  - Mac #1 can connect to Mac #2 by using its own localhost:50052

- **`-R 50060:localhost:50060`**: Reverse forward Mac #2's localhost:50060 → Mac #1's localhost:50060
  - Mac #2 can connect to Mac #1 by using its own localhost:50060

## Configuration Files

### Mac #2 Config (mac2_peers.json) - UPDATED ✅
```json
{
  "peers": {
    "mac1": {
      "address": "127.0.0.1:50060",
      "device_capabilities": {
        "model": "Mac #1",
        "chip": "Apple Silicon",
        "memory": 32768,
        "flops": {"fp32": 10.0, "fp16": 20.0, "int8": 40.0}
      }
    }
  }
}
```

### Mac #1 Config (mac1_peers.json)
```json
{
  "peers": {
    "mac2": {
      "address": "127.0.0.1:50052",
      "device_capabilities": {
        "model": "Mac #2",
        "chip": "Apple Silicon",
        "memory": 32768,
        "flops": {"fp32": 10.0, "fp16": 20.0, "int8": 40.0}
      }
    }
  }
}
```

## Step-by-Step Setup

### On Mac #1 (Remote Machine)

**Step 1: Create the bidirectional tunnel**
```bash
ssh -L 50052:localhost:50051 -R 50060:localhost:50060 -N remoteuser@192.168.2.1
```

Keep this running! Use `nohup`, `screen`, or `tmux` for persistence:
```bash
nohup ssh -L 50052:localhost:50051 -R 50060:localhost:50060 -N remoteuser@192.168.2.1 &
```

**Step 2: Copy mac1_peers.json to Mac #1**

**Step 3: Start exo on Mac #1**
```bash
python -m exo.main \
  --node-id mac1 \
  --node-port 50060 \
  --chatgpt-api-port 52416 \
  --discovery-module manual \
  --discovery-config-path mac1_peers.json \
  --disable-tui
```

### On Mac #2 (This Machine) - DONE ✅

```
✅ Config updated to point to localhost:50060
✅ Exo running (PID 30740)
✅ Listening on ports 50051 (node) and 52415 (API)
✅ Web UI: http://localhost:52415
```

## How Bidirectional Communication Works

1. **Mac #1 → Mac #2**:
   - Mac #1's exo connects to `localhost:50052`
   - SSH tunnel forwards to Mac #2's `localhost:50051`
   - Mac #2 receives connection

2. **Mac #2 → Mac #1**:
   - Mac #2's exo connects to `localhost:50060`
   - SSH reverse tunnel forwards to Mac #1's `localhost:50060`
   - Mac #1 receives connection

3. **Socket Protocol**:
   - Both directions use our new binary socket protocol
   - No gRPC, no mDNS
   - Direct tensor exchange

## Verification

### On Mac #1:
```bash
# Check tunnel is active
lsof -i :50052 -i :50060 | grep ssh

# Test forward tunnel
nc -zv localhost 50052

# Check exo is running
lsof -i :50060 | grep python
```

### On Mac #2 (this machine):
```bash
# Check reverse tunnel endpoint
lsof -i :50060 | grep ssh

# Check exo is running
lsof -i :50051 | grep python

# Test API
curl http://localhost:52415/topology
```

## Troubleshooting

### "Connection refused" on localhost:50060 (Mac #2 side)
- Make sure Mac #1 has created the reverse tunnel with `-R 50060:localhost:50060`
- Check: `lsof -i :50060` on Mac #2 should show ssh process

### "Connection refused" on localhost:50052 (Mac #1 side)
- Make sure Mac #2's exo is running on port 50051
- Check: `lsof -i :50051` on Mac #2 should show python process

### Nodes not discovering each other
- Verify both configs point to localhost (not 192.168.x.x)
- Check both nodes are running
- Check tunnel is active on Mac #1

## Current Status

✅ **Mac #2**: Running with updated config (PID 30740)
📋 **Mac #1**: Needs tunnel + exo startup

## Next Steps

1. On Mac #1: Run the SSH tunnel command with both `-L` and `-R`
2. On Mac #1: Start exo with mac1_peers.json
3. Watch the nodes discover each other via socket protocol
4. Open web UI and test distributed inference

The bidirectional tunnel enables both nodes to initiate connections to each other!
