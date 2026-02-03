# Two-Mac Setup with SSH Tunnel

## Architecture

```
Mac #1 (192.168.2.2)                Mac #2 (192.168.2.1)
    [Remote]                            [Local]

    Exo Node                           Exo Node
    Port: 50060              ←SSH←     Port: 50051
                            Tunnel     (YOU ARE HERE)

    Connects via:
    localhost:50052  ───────────→  192.168.2.1:50051
```

## Setup Instructions

### Mac #2 (THIS MACHINE - 192.168.2.1)

**Status: ✅ Already Running**

```bash
# Already started with:
python -m exo.main \
  --node-id mac2 \
  --node-port 50051 \
  --chatgpt-api-port 52415 \
  --discovery-module manual \
  --discovery-config-path mac2_peers.json \
  --disable-tui

# Process: Running on PID 20166
# Listening on: 50051 (node), 52415 (API)
# Web UI: http://localhost:52415
```

### Mac #1 (Remote - 192.168.2.2)

**Step 1: Create SSH Tunnel**
```bash
# On Mac #1, run this to tunnel into Mac #2:
ssh -L 50052:localhost:50051 -N remoteuser@192.168.2.1

# This creates: Mac #1's localhost:50052 → Mac #2's localhost:50051
# Keep this running in the background or use nohup/tmux
```

**Step 2: Start Exo on Mac #1**
```bash
# Copy mac1_peers.json to Mac #1, then run:
python -m exo.main \
  --node-id mac1 \
  --node-port 50060 \
  --chatgpt-api-port 52416 \
  --discovery-module manual \
  --discovery-config-path mac1_peers.json \
  --disable-tui
```

**Mac #1 Config (mac1_peers.json):**
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

## How It Works

1. **SSH Tunnel**: Mac #1 creates a local tunnel to Mac #2
2. **Mac #1's Exo**: Connects to its own localhost:50052
3. **Tunnel**: Forwards the connection to Mac #2:50051
4. **Socket Protocol**: Direct binary communication (no gRPC!)
5. **Bidirectional**: Both nodes can send/receive tensors

## Verification

### On Mac #2 (this machine):
```bash
# Check if exo is listening:
lsof -i :50051

# Check web UI:
curl http://localhost:52415

# View logs:
tail -f exo.log
```

### On Mac #1:
```bash
# Check tunnel is active:
lsof -i :50052

# Test tunnel connectivity:
nc -zv localhost 50052

# Check exo is running:
lsof -i :50060
```

## Port Summary

| Machine | Port  | Purpose              | Access                    |
|---------|-------|----------------------|---------------------------|
| Mac #2  | 50051 | Exo Node Socket      | Via tunnel from Mac #1    |
| Mac #2  | 52415 | ChatGPT API          | http://192.168.2.1:52415  |
| Mac #1  | 50052 | SSH Tunnel (local)   | Tunnels to Mac #2:50051   |
| Mac #1  | 50060 | Exo Node Socket      | Mac #2 connects here      |
| Mac #1  | 52416 | ChatGPT API          | http://192.168.2.2:52416  |

## Troubleshooting

### Mac #1 can't connect
```bash
# On Mac #1, test the tunnel:
nc -zv localhost 50052

# Should show: Connection to localhost port 50052 [tcp/*] succeeded!
# If not, restart the SSH tunnel
```

### Nodes not discovering each other
```bash
# Check manual discovery configs point to correct addresses
# Mac #1 should point to: 127.0.0.1:50052 (via tunnel)
# Mac #2 should point to: 192.168.2.2:50060 (direct)
```

### Connection refused
```bash
# Make sure:
# 1. SSH tunnel is running on Mac #1
# 2. Both exo nodes are started
# 3. No firewall blocking ports
```

## Current Status

✅ **Mac #2**: Running and ready (PID 20166)
⏳ **Mac #1**: Needs SSH tunnel + exo startup
📁 **Config**: mac1_peers.json created and ready to copy

## Next Steps

1. Copy `mac1_peers.json` to Mac #1
2. On Mac #1: Start SSH tunnel
3. On Mac #1: Start exo node
4. Watch both nodes discover each other
5. Open web UI and select a model to test

The socket-based protocol is ready for peer-to-peer tensor exchange!
