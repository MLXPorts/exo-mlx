#!/usr/bin/env python
"""
Direct peer connection - no discovery, just connect to specified IP:port.
"""
import asyncio
from typing import List, Callable, Optional

from exo.networking.discovery import Discovery
from exo.networking.peer_handle import PeerHandle
from exo.topology.device_capabilities import DeviceCapabilities, UNKNOWN_DEVICE_CAPABILITIES
from exo.helpers import DEBUG


class DirectDiscovery(Discovery):
    """
    Direct peer connection - specify IP and port, that's it.
    No mDNS, no UDP broadcast, no JSON files. Just connect.
    """

    def __init__(
        self,
        peer_host: str,
        peer_port: int,
        peer_id: Optional[str],
        create_peer_handle: Callable[[str, str, str, DeviceCapabilities], PeerHandle],
    ):
        self.peer_host = peer_host
        self.peer_port = peer_port
        self.peer_id = peer_id or f"peer-{peer_host}"
        self.create_peer_handle = create_peer_handle
        self.peer_handle: Optional[PeerHandle] = None

    async def start(self):
        """Connect directly to the specified peer."""
        if DEBUG >= 1:
            print(f"Connecting directly to {self.peer_host}:{self.peer_port}...")

        # Create peer handle
        peer_address = f"{self.peer_host}:{self.peer_port}"
        self.peer_handle = self.create_peer_handle(
            self.peer_id,
            peer_address,
            f"DIRECT ({self.peer_host})",
            UNKNOWN_DEVICE_CAPABILITIES
        )

        # Health check
        if not await self.peer_handle.health_check():
            if DEBUG >= 1:
                print(f"✗ Peer at {peer_address} is not healthy")
            self.peer_handle = None
        else:
            if DEBUG >= 1:
                print(f"✓ Connected to peer at {peer_address}")

    async def stop(self):
        """Nothing to stop."""
        pass

    async def discover_peers(self, wait_for_peers: int = 0) -> List[PeerHandle]:
        """Return the single peer we're connected to."""
        if self.peer_handle:
            return [self.peer_handle]
        return []
