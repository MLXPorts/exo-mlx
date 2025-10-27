#!/usr/bin/env python
"""
mDNS/Zeroconf-based discovery for exo.

Uses the same protocol as printers, AirPlay, AirDrop - works reliably across
all network types including link-local (169.254.x.x) addresses.
"""

import asyncio
import socket
import time
import json
from typing import Dict, List, Callable, Tuple, Optional
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceStateChange
from zeroconf.asyncio import AsyncZeroconf

from exo.networking.discovery import Discovery
from exo.networking.peer_handle import PeerHandle
from exo.topology.device_capabilities import DeviceCapabilities, device_capabilities, UNKNOWN_DEVICE_CAPABILITIES
from exo.helpers import DEBUG, DEBUG_DISCOVERY


class MDNSDiscovery(Discovery):
    """
    mDNS/Zeroconf-based peer discovery.

    Uses multicast DNS (same as printers/AirPlay) for reliable discovery across
    all network types including link-local (169.254.x.x) addresses.
    """

    SERVICE_TYPE = "_exo._tcp.local."

    def __init__(
        self,
        node_id: str,
        node_port: int,
        create_peer_handle: Callable[[str, str, str, DeviceCapabilities], PeerHandle],
        discovery_timeout: int = 30,
        device_capabilities: DeviceCapabilities = UNKNOWN_DEVICE_CAPABILITIES,
        allowed_node_ids: Optional[List[str]] = None,
    ):
        self.node_id = node_id
        self.node_port = node_port
        self.create_peer_handle = create_peer_handle
        self.discovery_timeout = discovery_timeout
        self.device_capabilities = device_capabilities
        self.allowed_node_ids = allowed_node_ids
        self.known_peers: Dict[str, Tuple[PeerHandle, float, float]] = {}

        self.azeroconf: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.browser: Optional[ServiceBrowser] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self):
        """Start mDNS service registration and browsing."""
        self.device_capabilities = await device_capabilities()

        # Store event loop for thread-safe task creation
        self.loop = asyncio.get_running_loop()

        # Create AsyncZeroconf instance
        self.azeroconf = AsyncZeroconf()

        # Register our service
        await self._register_service()

        # Start browsing for other services
        self.browser = ServiceBrowser(
            self.azeroconf.zeroconf,
            self.SERVICE_TYPE,
            handlers=[self._on_service_state_change]
        )

        if DEBUG_DISCOVERY >= 1:
            print(f"✓ mDNS discovery started for node {self.node_id}")

    async def stop(self):
        """Stop mDNS service."""
        if self.service_info and self.azeroconf:
            await self.azeroconf.async_unregister_service(self.service_info)
            if DEBUG_DISCOVERY >= 1:
                print(f"✓ Unregistered mDNS service for {self.node_id}")

        if self.azeroconf:
            await self.azeroconf.async_close()

    async def _register_service(self):
        """Register this node as an mDNS service."""
        # Get all local IP addresses
        addrs = []
        hostname = socket.gethostname()

        # Try to get all network interfaces
        try:
            # Get all addresses for this host
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET)
            addrs = [socket.inet_aton(info[4][0]) for info in addr_info]
        except Exception:
            # Fallback: just use primary address
            try:
                addrs = [socket.inet_aton(socket.gethostbyname(hostname))]
            except Exception:
                if DEBUG >= 1:
                    print(f"Warning: Could not determine local IP addresses")
                addrs = []

        # Create service properties
        properties = {
            "node_id": self.node_id,
            "device_capabilities": json.dumps(self.device_capabilities.to_dict()),
        }

        # Create service info
        service_name = f"{self.node_id}.{self.SERVICE_TYPE}"
        self.service_info = ServiceInfo(
            type_=self.SERVICE_TYPE,
            name=service_name,
            addresses=addrs,
            port=self.node_port,
            properties=properties,
            server=f"{hostname}.",
        )

        # Register the service
        await self.azeroconf.async_register_service(self.service_info)

        if DEBUG_DISCOVERY >= 1:
            print(f"✓ Registered mDNS service: {service_name} on port {self.node_port}")
            print(f"  Addresses: {[socket.inet_ntoa(addr) for addr in addrs]}")

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        """Handle service state changes (added/removed/updated).

        This is called from zeroconf's background thread, so we need to use
        call_soon_threadsafe to schedule the coroutine in the main event loop.
        """
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._handle_service_change(zeroconf, service_type, name, state_change),
                self.loop
            )

    async def _handle_service_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ):
        """Async handler for service state changes."""
        if state_change == ServiceStateChange.Added:
            await self._on_service_added(zeroconf, service_type, name)
        elif state_change == ServiceStateChange.Removed:
            await self._on_service_removed(name)
        elif state_change == ServiceStateChange.Updated:
            await self._on_service_updated(zeroconf, service_type, name)

    async def _on_service_added(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Handle a new service being discovered."""
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            if DEBUG_DISCOVERY >= 2:
                print(f"Could not get info for service: {name}")
            return

        # Extract node_id from properties
        node_id = info.properties.get(b"node_id")
        if node_id:
            node_id = node_id.decode("utf-8")
        else:
            if DEBUG_DISCOVERY >= 2:
                print(f"Service {name} has no node_id property")
            return

        # Skip our own service
        if node_id == self.node_id:
            return

        # Skip if not in allowed list
        if self.allowed_node_ids and node_id not in self.allowed_node_ids:
            if DEBUG_DISCOVERY >= 2:
                print(f"Ignoring peer {node_id} (not in allowed list)")
            return

        # Get device capabilities
        device_caps_json = info.properties.get(b"device_capabilities")
        if device_caps_json:
            device_caps_dict = json.loads(device_caps_json.decode("utf-8"))
            device_caps = DeviceCapabilities(**device_caps_dict)
        else:
            device_caps = UNKNOWN_DEVICE_CAPABILITIES

        # Get address and port
        if info.addresses:
            address = socket.inet_ntoa(info.addresses[0])
            port = info.port
            peer_address = f"{address}:{port}"

            # Create or update peer handle
            if node_id not in self.known_peers or self.known_peers[node_id][0].addr() != peer_address:
                peer_handle = self.create_peer_handle(
                    node_id,
                    peer_address,
                    f"mDNS ({address})",
                    device_caps
                )

                # Health check
                if not await peer_handle.health_check():
                    if DEBUG >= 1:
                        print(f"Peer {node_id} at {peer_address} is not healthy")
                    return

                if DEBUG >= 1:
                    print(f"✓ Discovered peer via mDNS: {node_id} at {peer_address}")

                self.known_peers[node_id] = (peer_handle, time.time(), time.time())
            else:
                # Update last seen time
                peer_handle, connected_at, _ = self.known_peers[node_id]
                self.known_peers[node_id] = (peer_handle, connected_at, time.time())

    async def _on_service_removed(self, name: str):
        """Handle a service being removed."""
        # Extract node_id from name
        node_id = name.split('.')[0]

        if node_id in self.known_peers:
            if DEBUG >= 1:
                print(f"Peer {node_id} removed via mDNS")
            del self.known_peers[node_id]

    async def _on_service_updated(self, zeroconf: Zeroconf, service_type: str, name: str):
        """Handle a service being updated."""
        # Treat as added
        await self._on_service_added(zeroconf, service_type, name)

    async def discover_peers(self, wait_for_peers: int = 0) -> List[PeerHandle]:
        """Get list of discovered peers."""
        if wait_for_peers > 0:
            while len(self.known_peers) < wait_for_peers:
                if DEBUG_DISCOVERY >= 2:
                    print(f"Current peers: {len(self.known_peers)}/{wait_for_peers}. Waiting...")
                await asyncio.sleep(0.1)

        return [peer_handle for peer_handle, _, _ in self.known_peers.values()]
