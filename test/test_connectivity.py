#!/usr/bin/env python
"""
Raw connectivity tests for exo peer-to-peer communication.
Tests UDP discovery and gRPC connectivity across different network interfaces.

Usage:
  # On machine 1 (server):
  python test_connectivity.py --mode server --port 50051

  # On machine 2 (client):
  python test_connectivity.py --mode client --host 192.168.1.100 --port 50051
"""

import socket
import asyncio
import argparse
import json
import time
import psutil
import ipaddress
from typing import List, Tuple


def get_all_interfaces() -> List[Tuple[str, str, str]]:
    """Get all network interfaces with their IP addresses and broadcast addresses."""
    interfaces = []
    for ifname, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                broadcast = getattr(addr, 'broadcast', None)
                if not broadcast and getattr(addr, 'netmask', None):
                    try:
                        net = ipaddress.IPv4Network(f"{addr.address}/{addr.netmask}", strict=False)
                        broadcast = str(net.broadcast_address)
                    except Exception:
                        broadcast = "255.255.255.255"
                interfaces.append((ifname, addr.address, broadcast or "255.255.255.255"))
    return interfaces


async def test_udp_broadcast(listen_port: int = 5555, broadcast_port: int = 5556):
    """Test UDP broadcast discovery."""
    print(f"\n=== UDP Broadcast Test ===")
    print(f"Listen Port: {listen_port}")
    print(f"Broadcast Port: {broadcast_port}")

    interfaces = get_all_interfaces()
    print(f"\nDetected {len(interfaces)} network interfaces:")
    for ifname, ip, broadcast in interfaces:
        print(f"  {ifname}: {ip} (broadcast: {broadcast})")

    # Start listener
    class ListenProtocol(asyncio.DatagramProtocol):
        def __init__(self):
            self.messages = []

        def datagram_received(self, data, addr):
            msg = data.decode('utf-8')
            self.messages.append((addr, msg))
            print(f"  ✓ Received from {addr}: {msg[:100]}")

    loop = asyncio.get_event_loop()
    listen_protocol = ListenProtocol()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: listen_protocol,
        local_addr=("0.0.0.0", listen_port)
    )

    print(f"\n✓ Listener started on 0.0.0.0:{listen_port}")

    # Broadcast from each interface
    print(f"\nBroadcasting test message from each interface...")
    for ifname, ip, broadcast in interfaces:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass

            sock.bind((ip, 0))

            message = json.dumps({
                "test": "connectivity",
                "interface": ifname,
                "source_ip": ip,
                "timestamp": time.time()
            })

            # Try subnet-specific broadcast
            sent_bytes = sock.sendto(message.encode('utf-8'), (broadcast, broadcast_port))
            print(f"  ✓ Sent {sent_bytes} bytes from {ifname} ({ip}) to {broadcast}:{broadcast_port}")

            # Also try global broadcast
            if broadcast != "255.255.255.255":
                sent_bytes = sock.sendto(message.encode('utf-8'), ("255.255.255.255", broadcast_port))
                print(f"  ✓ Sent {sent_bytes} bytes from {ifname} ({ip}) to 255.255.255.255:{broadcast_port}")

            sock.close()
        except Exception as e:
            print(f"  ✗ Failed to broadcast from {ifname} ({ip}): {e}")

    # Wait for responses
    print(f"\nWaiting 3 seconds for responses...")
    await asyncio.sleep(3)

    transport.close()

    print(f"\n✓ Received {len(listen_protocol.messages)} total messages")
    return len(listen_protocol.messages) > 0


async def test_tcp_raw(host: str, port: int):
    """Test raw TCP connectivity."""
    print(f"\n=== Raw TCP Test ===")
    print(f"Target: {host}:{port}")

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0
        )
        print(f"✓ TCP connection established to {host}:{port}")

        # Send test message
        test_msg = b"PING\n"
        writer.write(test_msg)
        await writer.drain()
        print(f"✓ Sent {len(test_msg)} bytes")

        # Try to read response
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            print(f"✓ Received {len(data)} bytes: {data[:100]}")
        except asyncio.TimeoutError:
            print(f"  (No response received, but connection works)")

        writer.close()
        await writer.wait_closed()
        return True

    except asyncio.TimeoutError:
        print(f"✗ Connection timeout to {host}:{port}")
        return False
    except Exception as e:
        print(f"✗ TCP connection failed: {e}")
        return False


async def test_grpc_connectivity(host: str, port: int):
    """Test gRPC connectivity."""
    print(f"\n=== gRPC Connectivity Test ===")
    print(f"Target: {host}:{port}")

    try:
        import grpc
        from exo.networking.grpc import node_service_pb2, node_service_pb2_grpc

        channel = grpc.aio.insecure_channel(
            f"{host}:{port}",
            options=[
                ("grpc.max_receive_message_length", 256 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 10000),
                ("grpc.keepalive_timeout_ms", 5000),
            ]
        )

        print(f"  Channel created, waiting for ready...")
        await asyncio.wait_for(channel.channel_ready(), timeout=10.0)
        print(f"✓ gRPC channel ready")

        stub = node_service_pb2_grpc.NodeServiceStub(channel)
        request = node_service_pb2.HealthCheckRequest()

        print(f"  Sending health check...")
        response = await asyncio.wait_for(stub.HealthCheck(request), timeout=5.0)
        print(f"✓ Health check response: is_healthy={response.is_healthy}")

        await channel.close()
        return True

    except asyncio.TimeoutError:
        print(f"✗ gRPC connection timeout")
        return False
    except Exception as e:
        print(f"✗ gRPC test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_server_mode(port: int):
    """Run a simple test server."""
    print(f"\n=== Running Test Server ===")
    print(f"Port: {port}")

    # Simple TCP echo server
    async def handle_client(reader, writer):
        addr = writer.get_extra_info('peername')
        print(f"✓ Client connected from {addr}")

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                print(f"  Received {len(data)} bytes from {addr}")
                writer.write(b"PONG\n")
                await writer.drain()
        except Exception as e:
            print(f"  Error handling client {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"  Client {addr} disconnected")

    server = await asyncio.start_server(handle_client, '0.0.0.0', port)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f'✓ Server listening on {addrs}')

    async with server:
        await server.serve_forever()


async def run_client_mode(host: str, port: int):
    """Run connectivity tests as client."""
    print(f"\n=== Running Connectivity Tests ===")
    print(f"Target: {host}:{port}")

    results = {
        "udp_broadcast": await test_udp_broadcast(),
        "tcp_raw": await test_tcp_raw(host, port),
        "grpc": await test_grpc_connectivity(host, port),
    }

    print(f"\n=== Test Results ===")
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {test_name}: {status}")

    all_pass = all(results.values())
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_pass else '✗ SOME TESTS FAILED'}")
    return all_pass


def main():
    parser = argparse.ArgumentParser(description="Test exo peer-to-peer connectivity")
    parser.add_argument("--mode", choices=["server", "client"], required=True,
                       help="Run as server or client")
    parser.add_argument("--host", default="127.0.0.1",
                       help="Target host (client mode only)")
    parser.add_argument("--port", type=int, default=50051,
                       help="Port for gRPC/TCP tests")
    parser.add_argument("--listen-port", type=int, default=5555,
                       help="UDP listen port")
    parser.add_argument("--broadcast-port", type=int, default=5556,
                       help="UDP broadcast port")

    args = parser.parse_args()

    if args.mode == "server":
        asyncio.run(run_server_mode(args.port))
    else:
        asyncio.run(run_client_mode(args.host, args.port))


if __name__ == "__main__":
    main()
