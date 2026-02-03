#!/usr/bin/env python
"""
Socket-based peer handle for direct TCP connections.
Compatible with SSH tunnels and manual port configuration.
"""

import asyncio
from typing import Optional, List
import numpy as np
import mlx.core as mx

from ..peer_handle import PeerHandle
from .protocol import (
    MessageType, HEADER_SIZE,
    pack_message, unpack_header,
    encode_health_check_request, decode_health_check_response,
    encode_send_prompt_request, decode_send_prompt_request,
    encode_send_tensor_request, decode_send_tensor_request,
    encode_send_tensor_response, decode_send_tensor_response,
    encode_send_result,
    encode_collect_topology_request, decode_collect_topology_response,
    encode_send_opaque_status,
    encode_shard, decode_shard,
)

from exo.inference.shard import Shard
from exo.inference.mlx_array import MLXArray
from exo.topology.topology import Topology
from exo.topology.device_capabilities import DeviceCapabilities, DeviceFlops
from exo.helpers import DEBUG


class SocketPeerHandle(PeerHandle):
    """
    Peer handle using raw TCP sockets with binary protocol.
    Designed for SSH tunnel compatibility and manual configuration.
    """

    def __init__(
        self,
        _id: str,
        address: str,
        desc: str,
        device_capabilities: DeviceCapabilities,
        timeout: float = 30.0
    ):
        self._id = _id
        self.address = address
        self.desc = desc
        self._device_capabilities = device_capabilities
        self.timeout = timeout

        # Parse address (host:port)
        if ':' in address:
            self.host, port_str = address.rsplit(':', 1)
            self.port = int(port_str)
        else:
            raise ValueError(f"Address must be in format host:port, got: {address}")

        # Connection state
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    def id(self) -> str:
        return self._id

    def addr(self) -> str:
        return self.address

    def description(self) -> str:
        return self.desc

    def device_capabilities(self) -> DeviceCapabilities:
        return self._device_capabilities

    async def connect(self) -> None:
        """Establish TCP connection."""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0
            )
            if DEBUG >= 2:
                print(f"Connected to {self._id}@{self.address}")
        except Exception as e:
            if DEBUG >= 2:
                print(f"Connection failed for {self._id}@{self.address}: {e}")
            raise

    async def is_connected(self) -> bool:
        """Check if connection is active."""
        if self.writer is None:
            return False
        return not self.writer.is_closing()

    async def disconnect(self) -> None:
        """Close connection."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None

    async def _ensure_connected(self):
        """Ensure connection is active, reconnect if needed."""
        if not await self.is_connected():
            await self.connect()

    async def _send_message(self, msg_type: MessageType, payload: bytes) -> None:
        """Send a message to peer."""
        async with self._lock:
            await self._ensure_connected()
            message = pack_message(msg_type, payload)
            self.writer.write(message)
            await self.writer.drain()

    async def _recv_message(self) -> tuple[MessageType, bytes]:
        """Receive a message from peer."""
        async with self._lock:
            await self._ensure_connected()

            # Read header
            header = await asyncio.wait_for(
                self.reader.readexactly(HEADER_SIZE),
                timeout=self.timeout
            )
            msg_type, payload_len = unpack_header(header)

            # Read payload
            payload = await asyncio.wait_for(
                self.reader.readexactly(payload_len),
                timeout=self.timeout
            )

            return msg_type, payload

    async def _send_recv(self, send_type: MessageType, send_payload: bytes, expected_type: MessageType) -> bytes:
        """Send a message and wait for response."""
        await self._send_message(send_type, send_payload)
        recv_type, recv_payload = await self._recv_message()

        if recv_type != expected_type:
            raise ValueError(f"Expected message type {expected_type}, got {recv_type}")

        return recv_payload

    async def health_check(self) -> bool:
        """Check if peer is healthy."""
        try:
            payload = encode_health_check_request()
            response = await asyncio.wait_for(
                self._send_recv(
                    MessageType.HEALTH_CHECK_REQUEST,
                    payload,
                    MessageType.HEALTH_CHECK_RESPONSE
                ),
                timeout=5.0
            )
            return decode_health_check_response(response)
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            if DEBUG >= 4:
                print(f"Health check failed for {self._id}@{self.address}: {e}")
                import traceback
                traceback.print_exc()
            return False

    async def send_prompt(
        self,
        shard: Shard,
        prompt: str,
        inference_state: Optional[dict] = None,
        request_id: Optional[str] = None
    ) -> Optional[MLXArray]:
        """Send prompt to peer."""
        await self._ensure_connected()

        shard_dict = encode_shard(shard.model_id, shard.start_layer, shard.end_layer, shard.n_layers)
        payload = encode_send_prompt_request(shard_dict, prompt, request_id, inference_state)

        await self._send_message(MessageType.SEND_PROMPT_REQUEST, payload)
        # Note: Prompt requests may not return immediately (streaming response)
        return None

    async def send_tensor(
        self,
        shard: Shard,
        tensor: MLXArray,
        inference_state: Optional[dict] = None,
        request_id: Optional[str] = None
    ) -> Optional[MLXArray]:
        """Send tensor to peer and receive result."""
        await self._ensure_connected()

        shard_dict = encode_shard(shard.model_id, shard.start_layer, shard.end_layer, shard.n_layers)
        tensor_bytes = tensor.tobytes()
        payload = encode_send_tensor_request(
            shard_dict,
            tensor_bytes,
            tensor.shape,
            str(tensor.dtype),
            request_id,
            inference_state
        )

        response = await self._send_recv(
            MessageType.SEND_TENSOR_REQUEST,
            payload,
            MessageType.SEND_TENSOR_RESPONSE
        )

        result = decode_send_tensor_response(response)
        if result is None:
            return None

        metadata, tensor_data = result
        tensor_meta = metadata['tensor']

        # Reconstruct MLXArray from bytes
        np_array = np.frombuffer(tensor_data, dtype=tensor_meta['dtype']).reshape(tensor_meta['shape'])
        # Convert to MLX array
        from exo.inference.mlx_array import array_from_bytes
        return array_from_bytes(tensor_data, tuple(tensor_meta['shape']), tensor_meta['dtype'])

    async def send_example(
        self,
        shard: Shard,
        example: MLXArray,
        target: MLXArray,
        length: MLXArray,
        train: bool,
        request_id: Optional[str] = None
    ) -> Optional[MLXArray]:
        """Send training example to peer."""
        # TODO: Implement training protocol
        raise NotImplementedError("Training not yet implemented for socket protocol")

    async def send_loss(
        self,
        shard: Shard,
        tensor: MLXArray,
        request_id: Optional[str] = None
    ) -> Optional[MLXArray]:
        """Send loss gradient to peer."""
        # TODO: Implement training protocol
        raise NotImplementedError("Training not yet implemented for socket protocol")

    async def collect_topology(self, visited: set[str], max_depth: int) -> Topology:
        """Collect topology information from peer."""
        await self._ensure_connected()

        payload = encode_collect_topology_request(visited, max_depth)
        response = await self._send_recv(
            MessageType.COLLECT_TOPOLOGY_REQUEST,
            payload,
            MessageType.COLLECT_TOPOLOGY_RESPONSE
        )

        data = decode_collect_topology_response(response)

        topology = Topology()

        # Add nodes
        for node_id, capabilities in data['nodes'].items():
            device_capabilities = DeviceCapabilities(
                model=capabilities['model'],
                chip=capabilities['chip'],
                memory=capabilities['memory'],
                flops=DeviceFlops(
                    fp16=capabilities['flops']['fp16'],
                    fp32=capabilities['flops']['fp32'],
                    int8=capabilities['flops']['int8']
                )
            )
            topology.update_node(node_id, device_capabilities)

        # Add edges
        for node_id, connections in data['peer_graph'].items():
            for conn in connections:
                topology.add_edge(node_id, conn['to_id'], conn['description'])

        return topology

    async def send_result(self, request_id: str, result: List[int], is_finished: bool) -> None:
        """Send inference result to peer."""
        await self._ensure_connected()

        # Handle tensor results
        tensor_data = None
        shape = None
        dtype = None
        if isinstance(result, np.ndarray):
            tensor_data = result.tobytes()
            shape = result.shape
            dtype = str(result.dtype)
            result = []

        payload = encode_send_result(request_id, result, is_finished, tensor_data, shape, dtype)
        await self._send_message(MessageType.SEND_RESULT, payload)

    async def send_opaque_status(self, request_id: str, status: str) -> None:
        """Send opaque status update to peer."""
        await self._ensure_connected()

        payload = encode_send_opaque_status(request_id, status)
        await self._send_message(MessageType.SEND_OPAQUE_STATUS, payload)

    def serialize_inference_state(self, inference_state: dict) -> dict:
        """Serialize inference state (no-op for socket protocol, handled in encoding)."""
        # TODO: Implement proper inference state serialization
        return inference_state
