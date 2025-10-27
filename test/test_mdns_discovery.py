#!/usr/bin/env python
"""
Test mDNS/Zeroconf discovery.

Usage:
  # Terminal 1:
  python test/test_mdns_discovery.py --node-id node1 --port 50051

  # Terminal 2:
  python test/test_mdns_discovery.py --node-id node2 --port 50052
"""

import asyncio
import argparse
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exo.networking.mdns.mdns_discovery import MDNSDiscovery
from exo.networking.grpc.grpc_peer_handle import GRPCPeerHandle
from exo.topology.device_capabilities import DeviceCapabilities, DeviceFlops
from exo.helpers import DEBUG_DISCOVERY, get_all_ip_addresses_and_interfaces


def create_peer_handle(peer_id: str, address: str, desc: str, device_capabilities: DeviceCapabilities):
    """Factory for creating peer handles."""
    return GRPCPeerHandle(peer_id, address, desc, device_capabilities)


async def main():
    parser = argparse.ArgumentParser(description="Test mDNS discovery")
    parser.add_argument("--node-id", required=True, help="Node ID")
    parser.add_argument("--port", type=int, default=50051, help="gRPC port")
    parser.add_argument("--wait-for-peers", type=int, default=0, help="Wait for N peers before listing")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"🔍 mDNS DISCOVERY TEST")
    print(f"{'='*60}")
    print(f"Node ID: {args.node_id}")
    print(f"Port: {args.port}")

    # Show network interfaces
    print(f"\n📡 Network Interfaces:")
    interfaces = get_all_ip_addresses_and_interfaces()
    for ip, ifname in interfaces:
        print(f"   {ifname}: {ip}")

    # Create device capabilities
    device_caps = DeviceCapabilities(
        model="Test",
        chip="Test",
        memory=0,
        flops=DeviceFlops(fp32=0, fp16=0, int8=0)
    )

    # Create discovery
    discovery = MDNSDiscovery(
        node_id=args.node_id,
        node_port=args.port,
        create_peer_handle=create_peer_handle,
        device_capabilities=device_caps,
    )

    print(f"\n🚀 Starting mDNS discovery...")
    await discovery.start()
    print(f"✓ mDNS discovery started\n")

    if args.wait_for_peers > 0:
        print(f"Waiting for {args.wait_for_peers} peer(s)...")

    try:
        # Discover peers
        peers = await discovery.discover_peers(wait_for_peers=args.wait_for_peers)

        print(f"\n{'='*60}")
        print(f"📋 DISCOVERED PEERS: {len(peers)}")
        print(f"{'='*60}")
        for peer in peers:
            print(f"  • {peer.id()} at {peer.addr()}")
            print(f"    {peer.description()}")
            print(f"    Capabilities: {peer.device_capabilities().model}")

        if not peers and args.wait_for_peers == 0:
            print("  (No peers found yet - discovery is ongoing)")

        # Keep running to allow continuous discovery
        print(f"\n{'='*60}")
        print(f"🔄 Continuing discovery... (Press Ctrl+C to stop)")
        print(f"{'='*60}\n")

        while True:
            await asyncio.sleep(5)
            current_peers = await discovery.discover_peers()
            if len(current_peers) != len(peers):
                peers = current_peers
                print(f"\n📋 Peers updated: {len(peers)} peer(s)")
                for peer in peers:
                    print(f"  • {peer.id()} at {peer.addr()}")

    except KeyboardInterrupt:
        print(f"\n\n🛑 Stopping...")
    finally:
        await discovery.stop()
        print("✓ Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
