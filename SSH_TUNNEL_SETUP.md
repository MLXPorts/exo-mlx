# SSH Tunnel Configuration for Exo

Exo now uses a lightweight socket-based protocol instead of gRPC, making it ideal for SSH tunnel deployments.

## Quick Start

### 1. Set up SSH Tunnels (on your local machine)

Forward the remote node's port to your local machine:

```bash
# Forward remote node's port 50051 to local port 49703
ssh -L 49703:10.0.0.151:50051 -N remoteuser@10.0.0.151
```

For multiple remote nodes, use multiple `-L` flags:

```bash
ssh -L 49703:10.0.0.151:50051 -L 52415:10.0.0.152:50051 -N remoteuser@10.0.0.151
```

### 2. Create Configuration File

Create `peers.json`:

```json
{
  "peers": {
    "remote-node-1": {
      "address": "127.0.0.1:49703",
      "device_capabilities": {
        "model": "Remote MacBook Pro",
        "chip": "Apple M3 Max",
        "memory": 65536,
        "flops": {
          "fp32": 14.0,
          "fp16": 28.0,
          "int8": 56.0
        }
      }
    }
  }
}
```

### 3. Start Exo Node

On the local machine:

```bash
exo --discovery-module manual --discovery-config-path peers.json
```

On the remote machine:

```bash
exo --node-port 50051
```

## Architecture Changes

### What Changed

- **Removed**: gRPC, mDNS/Zeroconf
- **Added**: Raw TCP socket protocol with binary messaging
- **Benefits**:
  - SSH tunnel compatible
  - Lower latency
  - Simpler deployment
  - No protobuf compilation needed

### Binary Protocol

Messages use a simple binary format:

```
[4 bytes: magic 'EXO\x01']
[1 byte: message type]
[4 bytes: payload length]
[N bytes: payload]
```

## Discovery Modes

### Manual Discovery (Recommended for SSH Tunnels)

Use when you have SSH tunnels or known peer addresses:

```bash
exo --discovery-module manual --discovery-config-path peers.json
```

### Direct Discovery

Connect to a single known peer:

```bash
exo --discovery-module direct --peer-host 127.0.0.1 --peer-port 49703
```

### UDP Discovery (Local Networks)

For local network discovery without tunnels:

```bash
exo --discovery-module udp
```

### TCP Discovery (Local Networks)

TCP-based discovery for local networks:

```bash
exo --discovery-module tcp
```

## SSH Tunnel Best Practices

### Use Persistent Tunnels

Use `autossh` or `systemd` to keep tunnels alive:

```bash
autossh -M 0 -N -L 49703:10.0.0.151:50051 remoteuser@10.0.0.151
```

### Reverse Tunnels (Remote to Local)

If the local machine is accessible from remote:

On remote machine:
```bash
ssh -R 50051:localhost:50051 -N localuser@local.machine
```

On local machine's `peers.json`:
```json
{
  "peers": {
    "remote-node": {
      "address": "127.0.0.1:50051",
      ...
    }
  }
}
```

### Multiple Remote Networks

For peers in different networks, use separate tunnels:

```bash
ssh -L 49703:192.168.1.10:50051 -N gateway1@network1
ssh -L 52415:192.168.2.20:50051 -N gateway2@network2
```

## Port Configuration

Default ports:
- Node communication: `50051`
- ChatGPT API: `52415`
- Discovery (UDP/TCP): `5678`

Change with:
```bash
exo --node-port 50051 --chatgpt-api-port 52415
```

## Troubleshooting

### Connection Refused

Check that:
1. SSH tunnel is active: `lsof -i :49703`
2. Remote node is running
3. Port numbers match in config

### Firewall Issues

Ensure local firewall allows the tunnel ports:
```bash
# macOS
sudo pfctl -e
```

### Health Check Failures

Test the connection manually:
```bash
nc -zv 127.0.0.1 49703
```

## Migration from gRPC

If you have existing gRPC configs:

1. Remove `grpcio`, `grpcio-tools`, `protobuf`, and `zeroconf` from environment
2. Update configs to use new discovery modules
3. Restart all nodes

No model or inference changes required - the protocol change is transparent to the inference layer.
