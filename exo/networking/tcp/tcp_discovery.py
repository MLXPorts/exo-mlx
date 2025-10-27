#!/usr/bin/env python
"""
TCP-based peer discovery - more reliable than UDP broadcast.
Listens on a TCP port and accepts connections from peers announcing themselves.
"""
import asyncio
import json
import socket
from typing import Callable, Optional, List, Dict
from exo.networking.discovery import Discovery
from exo.networking.peer_handle import PeerHandle
from exo.topology.device_capabilities import DeviceCapabilities, device_capabilities
from exo.helpers import DEBUG_DISCOVERY, get_all_ip_addresses_and_interfaces


class TCPDiscovery(Discovery):
    """
    TCP-based discovery - peers connect to each other via TCP to announce themselves.
    More reliable than UDP broadcast which can be blocked by firewalls.
    """

    def __init__(
        self,
        node_id: str,
        node_port: int,
        listen_port: int,
        create_peer_handle: Callable[[str, str, str, DeviceCapabilities], PeerHandle],
        broadcast_interval: int = 5,
        device_capabilities: Optional[DeviceCapabilities] = None,
    ):
        self.node_id = node_id
        self.node_port = node_port
        self.listen_port = listen_port
        self.create_peer_handle = create_peer_handle
        self.broadcast_interval = broadcast_interval
        self.device_capabilities = device_capabilities
        self.known_peers: Dict[str, PeerHandle] = {}
        self.server = None
        self.broadcast_task = None
        self.cleanup_task = None

    async def start(self):
        """Start TCP discovery server and broadcast task."""
        if self.device_capabilities is None:
            self.device_capabilities = await device_capabilities()

        # Start TCP server to listen for peer announcements
        self.server = await asyncio.start_server(
            self._handle_peer_connection,
            "0.0.0.0",
            self.listen_port
        )

        if DEBUG_DISCOVERY >= 1:
            print(f"TCP Discovery listening on port {self.listen_port}")

        # Start broadcasting to known peers
        self.broadcast_task = asyncio.create_task(self._broadcast_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_unhealthy_peers())

    async def stop(self):
        """Stop TCP discovery."""
        if self.broadcast_task:
            self.broadcast_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def discover_peers(self, wait_for_peers: int = 0) -> List[PeerHandle]:
        """Return discovered peers."""
        if wait_for_peers > 0:
            while len(self.known_peers) < wait_for_peers:
                if DEBUG_DISCOVERY >= 2:
                    print(f"Waiting for peers: {len(self.known_peers)}/{wait_for_peers}")
                await asyncio.sleep(0.5)
        return list(self.known_peers.values())

    async def _handle_peer_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming TCP connection from a peer."""
        try:
            # Read announcement message
            data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            if not data:
                return

            message = json.loads(data.decode('utf-8'))

            if message.get('type') != 'announce':
                return

            peer_id = message.get('node_id')
            peer_port = message.get('grpc_port')
            peer_addr = writer.get_extra_info('peername')[0]
            peer_capabilities = DeviceCapabilities(**message.get('device_capabilities', {}))

            if peer_id == self.node_id:
                # Don't add ourselves
                return

            if DEBUG_DISCOVERY >= 2:
                print(f"Received TCP announcement from {peer_id} at {peer_addr}:{peer_port}")

            # Add or update peer
            if peer_id not in self.known_peers:
                peer_handle = self.create_peer_handle(
                    peer_id,
                    f"{peer_addr}:{peer_port}",
                    f"TCP ({peer_addr})",
                    peer_capabilities
                )

                # Verify peer is healthy
                if await peer_handle.health_check():
                    self.known_peers[peer_id] = peer_handle
                    if DEBUG_DISCOVERY >= 1:
                        print(f"✓ Discovered peer {peer_id} via TCP at {peer_addr}:{peer_port}")

            # Send acknowledgment
            response = {
                "type": "announce",
                "node_id": self.node_id,
                "grpc_port": self.node_port,
                "device_capabilities": self.device_capabilities.to_dict()
            }
            writer.write(json.dumps(response).encode('utf-8'))
            await writer.drain()

        except Exception as e:
            if DEBUG_DISCOVERY >= 2:
                print(f"Error handling peer connection: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _broadcast_loop(self):
        """Periodically announce ourselves to potential peers on the network."""
        while True:
            try:
                await asyncio.sleep(self.broadcast_interval)

                # Get all local IPs and try to connect to other machines on same subnets
                all_ips = get_all_ip_addresses_and_interfaces()

                for ip, _ in all_ips:
                    # Skip localhost
                    if ip.startswith("127."):
                        continue

                    # Try to announce to other potential peers on the same subnet
                    # For now, just try common IPs in the subnet
                    subnet_base = '.'.join(ip.split('.')[:-1])

                    # Try a few common host IPs
                    for host_num in [1, 2, 10, 100, 187]:  # Common router/host IPs
                        target_ip = f"{subnet_base}.{host_num}"
                        if target_ip == ip:
                            continue

                        await self._announce_to_peer(target_ip)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if DEBUG_DISCOVERY >= 2:
                    print(f"Error in broadcast loop: {e}")

    async def _announce_to_peer(self, peer_ip: str):
        """Announce ourselves to a specific peer IP."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer_ip, self.listen_port),
                timeout=1.0
            )

            # Send announcement
            message = {
                "type": "announce",
                "node_id": self.node_id,
                "grpc_port": self.node_port,
                "device_capabilities": self.device_capabilities.to_dict()
            }

            writer.write(json.dumps(message).encode('utf-8'))
            await writer.drain()

            # Wait for response
            data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            if data:
                response = json.loads(data.decode('utf-8'))
                peer_id = response.get('node_id')

                if peer_id and peer_id != self.node_id and peer_id not in self.known_peers:
                    peer_port = response.get('grpc_port')
                    peer_capabilities = DeviceCapabilities(**response.get('device_capabilities', {}))

                    peer_handle = self.create_peer_handle(
                        peer_id,
                        f"{peer_ip}:{peer_port}",
                        f"TCP ({peer_ip})",
                        peer_capabilities
                    )

                    if await peer_handle.health_check():
                        self.known_peers[peer_id] = peer_handle
                        if DEBUG_DISCOVERY >= 1:
                            print(f"✓ Discovered peer {peer_id} via TCP broadcast at {peer_ip}:{peer_port}")

            writer.close()
            await writer.wait_closed()

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            # Expected - peer might not exist at this IP
            pass
        except Exception as e:
            if DEBUG_DISCOVERY >= 3:
                print(f"Error announcing to {peer_ip}: {e}")

    async def _cleanup_unhealthy_peers(self):
        """Periodically remove unhealthy peers."""
        while True:
            try:
                await asyncio.sleep(30)

                unhealthy = []
                for peer_id, peer_handle in self.known_peers.items():
                    if not await peer_handle.health_check():
                        unhealthy.append(peer_id)

                for peer_id in unhealthy:
                    if DEBUG_DISCOVERY >= 1:
                        print(f"Removing unhealthy peer: {peer_id}")
                    del self.known_peers[peer_id]

            except asyncio.CancelledError:
                break
            except Exception as e:
                if DEBUG_DISCOVERY >= 2:
                    print(f"Error in cleanup task: {e}")
