# Connectivity Testing for exo-mlx

This document explains how to test peer-to-peer connectivity between exo nodes, especially across different network types including 169.254.x.x link-local addresses.

## Overview

exo uses two primary communication methods:
1. **UDP Broadcast Discovery** - For finding peers on the local network
2. **gRPC** - For actual model inference communication

## Quick Test

### On Machine 1 (Server):
```bash
python test/test_connectivity.py --mode server --port 50051
```

### On Machine 2 (Client):
```bash
# Replace 192.168.1.100 with Machine 1's IP
python test/test_connectivity.py --mode client --host 192.168.1.100 --port 50051
```

## What Gets Tested

The connectivity test performs:

1. **UDP Broadcast Discovery Test**
   - Detects all network interfaces
   - Broadcasts discovery messages on each interface
   - Uses proper broadcast addresses (including 169.254/16 ranges)
   - Verifies messages can be received

2. **Raw TCP Test**
   - Tests basic TCP connectivity
   - Useful for diagnosing firewall issues

3. **gRPC Health Check Test**
   - Tests full gRPC stack
   - Verifies protocol-level communication

## Link-Local (169.254.x.x) Addresses

### What Are They?

Link-local addresses (169.254.x.x) are auto-assigned when no DHCP server is available. They're commonly used on:
- Direct Ethernet connections between Macs
- Thunderbolt networks
- Ad-hoc wireless networks

### How exo Handles Them

As of commit `7a6aa72`, exo correctly handles link-local addresses by:

1. **Using `psutil` to get actual broadcast addresses**
   - Respects OS-provided broadcast addresses
   - Computes from netmask if needed (handles /16, /24, etc.)

2. **Dual broadcast strategy**
   - Sends to subnet-specific broadcast (e.g., 169.254.255.255 for /16)
   - Also sends to global broadcast (255.255.255.255) as fallback

3. **Per-interface binding**
   - Binds to specific interface IP before broadcasting
   - Ensures broadcasts go out the correct interface

### Code Location

See `exo/networking/udp/udp_discovery.py`:
- `get_broadcast_address()` - Computes correct broadcast for any subnet
- `BroadcastProtocol` - Handles dual broadcast strategy

## Common Issues

### UDP Discovery Not Working

**Symptoms**: Nodes don't see each other

**Possible Causes**:
1. **Firewall blocking UDP**
   ```bash
   # On macOS, check firewall:
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
   ```

2. **Wrong broadcast address**
   - Check with: `ifconfig` or `ip addr`
   - Verify netmask is correct (/16 for link-local, usually /24 for others)

3. **Different subnets**
   - Broadcasts don't cross subnet boundaries
   - Use `--allowed-interface-types` to filter

### gRPC Connection Fails

**Symptoms**: "Connection timeout" or "Connection refused"

**Possible Causes**:
1. **Firewall blocking TCP**
   ```bash
   # Test manually:
   nc -zv <peer-ip> 50051
   ```

2. **Wrong IP address**
   - Verify with: `python -c "from exo.helpers import get_all_ip_addresses_and_interfaces; print(get_all_ip_addresses_and_interfaces())"`

3. **Network MTU issues**
   - gRPC uses large messages (up to 256MB)
   - Check MTU: `ifconfig | grep mtu`
   - Link-local typically has MTU 1500

## Advanced Debugging

### Enable Debug Output

```bash
# In Python code:
from exo.helpers import DEBUG, DEBUG_DISCOVERY

DEBUG = 2  # General debugging
DEBUG_DISCOVERY = 2  # Discovery-specific
```

### Packet Capture

```bash
# Capture UDP discovery packets:
sudo tcpdump -i any -n udp port 5555 or udp port 5556

# Capture gRPC traffic:
sudo tcpdump -i any -n tcp port 50051
```

### Test Specific Interface

```bash
# Find interface name:
ifconfig | grep -B 1 "169.254"

# Then in exo, use:
--allowed-interface-types ethernet
```

## Network Topology Considerations

### Thunderbolt Networks
- Usually creates `bridge` interfaces
- Link-local (169.254.x.x) addresses
- MTU typically 1500
- **Fast**: 10-40 Gbps

### Direct Ethernet
- Usually `en` interfaces
- Can be link-local or static
- Check with: `ifconfig en0 | grep inet`

### WiFi/Ethernet Mix
- Different interfaces may have different MTUs
- Use `--allowed-interface-types` to prefer wired

## Testing Checklist

- [ ] Both machines can ping each other
- [ ] Firewall allows UDP ports 5555-5556
- [ ] Firewall allows TCP port 50051
- [ ] Correct broadcast address computed
- [ ] gRPC health check succeeds
- [ ] UDP discovery sees peer
- [ ] Can send/receive model tensors

## Example Session

```bash
# Machine 1 (Mac Studio):
$ python test/test_connectivity.py --mode server --port 50051
=== Running Test Server ===
Port: 50051
✓ Server listening on ('0.0.0.0', 50051)
✓ Client connected from ('169.254.10.20', 54321)

# Machine 2 (MacBook):
$ python test/test_connectivity.py --mode client --host 169.254.10.10 --port 50051
=== Running Connectivity Tests ===
Target: 169.254.10.10:50051

Detected 3 network interfaces:
  en0: 169.254.10.20 (broadcast: 169.254.255.255)
  ...

✓ UDP broadcast test PASSED
✓ TCP raw test PASSED
✓ gRPC test PASSED

Overall: ✓ ALL TESTS PASSED
```

## Novel Solutions

If standard networking fails, consider:

### 1. Multicast Instead of Broadcast
```python
# Join multicast group 224.0.0.251 (mDNS)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, ...)
```

### 2. Direct Socket Pair (Unix Domain Sockets)
- For same-machine testing
- Much faster than TCP

### 3. Custom Relay Node
- Use third machine with connectivity to both
- Acts as packet forwarder

### 4. USB/Thunderbolt Direct
- Use usbmuxd or similar
- Bypass network layer entirely
