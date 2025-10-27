#!/usr/bin/env python
"""
Dummy responder for testing exo connectivity.
Responds to UDP broadcasts and gRPC health checks.

Usage:
  python test/dummy_responder.py --port 50051 --udp-port 5556
"""

import asyncio
import argparse
import socket
import json
import time
from typing import Tuple
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exo.helpers import get_all_ip_addresses_and_interfaces


class UDPResponder(asyncio.DatagramProtocol):
    """Responds to UDP discovery broadcasts"""

    def __init__(self, node_id: str, grpc_port: int):
        self.node_id = node_id
        self.grpc_port = grpc_port
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        print(f"✓ UDP responder listening on port {transport.get_extra_info('sockname')[1]}")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        try:
            message = json.loads(data.decode('utf-8'))
            print(f"\n📨 UDP from {addr[0]}:{addr[1]}")
            print(f"   Message: {message}")

            if message.get('type') == 'discovery':
                # Send discovery response
                response = {
                    "type": "discovery",
                    "node_id": self.node_id,
                    "grpc_port": self.grpc_port,
                    "device_capabilities": {
                        "model": "DummyResponder",
                        "chip": "Test",
                        "memory": 0,
                        "flops": {"fp32": 0, "fp16": 0, "int8": 0}
                    },
                    "priority": 100,
                    "interface_name": "test",
                    "interface_type": "test",
                    "timestamp": time.time()
                }

                # Send response back to sender
                response_data = json.dumps(response).encode('utf-8')
                self.transport.sendto(response_data, addr)
                print(f"✓ Sent discovery response to {addr[0]}:{addr[1]}")

        except json.JSONDecodeError:
            print(f"✗ Invalid JSON from {addr}")
        except Exception as e:
            print(f"✗ Error handling UDP: {e}")


async def run_udp_responder(port: int, node_id: str, grpc_port: int):
    """Start UDP responder"""
    loop = asyncio.get_event_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPResponder(node_id, grpc_port),
        local_addr=('0.0.0.0', port)
    )

    return transport


async def run_grpc_responder(port: int):
    """Start gRPC responder"""
    try:
        import grpc
        from exo.networking.grpc import node_service_pb2, node_service_pb2_grpc

        class DummyNodeService(node_service_pb2_grpc.NodeServiceServicer):
            async def HealthCheck(self, request, context):
                print(f"\n📨 gRPC HealthCheck from {context.peer()}")
                return node_service_pb2.HealthCheckResponse(is_healthy=True)

            async def GetInferenceResult(self, request, context):
                print(f"\n📨 gRPC GetInferenceResult from {context.peer()}")
                # Return dummy response
                return node_service_pb2.GetInferenceResultResponse(
                    is_finished=True,
                    result=b"dummy_result"
                )

        server = grpc.aio.server()
        node_service_pb2_grpc.add_NodeServiceServicer_to_server(
            DummyNodeService(), server
        )

        server.add_insecure_port(f'[::]:{port}')
        await server.start()

        print(f"✓ gRPC responder listening on port {port}")
        return server

    except ImportError:
        print("✗ gRPC not available, skipping gRPC responder")
        return None


async def run_tcp_echo_server(port: int):
    """Simple TCP echo server for raw connectivity testing"""

    async def handle_client(reader, writer):
        addr = writer.get_extra_info('peername')
        print(f"\n📨 TCP connection from {addr[0]}:{addr[1]}")

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break

                message = data.decode('utf-8', errors='ignore').strip()
                print(f"   Received: {message[:100]}")

                # Echo back
                writer.write(b"PONG\n")
                await writer.drain()
                print(f"✓ Sent PONG to {addr[0]}:{addr[1]}")

        except Exception as e:
            print(f"✗ Error handling TCP client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"   Closed connection from {addr[0]}:{addr[1]}")

    server = await asyncio.start_server(handle_client, '0.0.0.0', port + 100)
    print(f"✓ TCP echo server listening on port {port + 100}")
    return server


async def main():
    parser = argparse.ArgumentParser(description="Dummy responder for exo connectivity testing")
    parser.add_argument("--port", type=int, default=50051, help="gRPC port")
    parser.add_argument("--udp-port", type=int, default=5556, help="UDP broadcast port")
    parser.add_argument("--node-id", default="dummy-responder", help="Node ID")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"🚀 DUMMY RESPONDER STARTING")
    print(f"{'='*60}")
    print(f"Node ID: {args.node_id}")
    print(f"gRPC Port: {args.port}")
    print(f"UDP Port: {args.udp_port}")
    print(f"TCP Echo Port: {args.port + 100}")

    # Show all available network interfaces
    print(f"\n📡 Available Network Interfaces:")
    interfaces = get_all_ip_addresses_and_interfaces()
    for ip, ifname in interfaces:
        print(f"   {ifname}: {ip}")

    print(f"\n{'='*60}\n")

    # Start all responders
    udp_transport = await run_udp_responder(args.udp_port, args.node_id, args.port)
    grpc_server = await run_grpc_responder(args.port)
    tcp_server = await run_tcp_echo_server(args.port)

    print(f"\n✅ All responders started. Waiting for connections...\n")
    print(f"Press Ctrl+C to stop\n")

    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\n🛑 Shutting down...")
    finally:
        # Cleanup
        udp_transport.close()
        if grpc_server:
            await grpc_server.stop(grace=1)
        tcp_server.close()
        await tcp_server.wait_closed()
        print("✓ Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
