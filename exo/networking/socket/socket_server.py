#!/usr/bin/env python
"""
Socket-based server for receiving peer connections.
Compatible with SSH tunnels and direct connections.
"""

import asyncio
from typing import Optional
import numpy as np
import mlx.core as mx

from .protocol import (
    MessageType, HEADER_SIZE,
    pack_message, unpack_header,
    encode_health_check_response,
    decode_send_prompt_request, decode_send_tensor_request,
    encode_send_tensor_response,
    decode_collect_topology_request, encode_collect_topology_response,
    decode_send_result, decode_send_opaque_status,
)

from exo import DEBUG
from exo.inference.shard import Shard
from exo.inference.mlx_array import array_from_bytes
from exo.orchestration import Node


class SocketServer:
    """
    Socket-based server for handling incoming peer connections.
    Replaces gRPC server with raw TCP sockets.
    """

    def __init__(self, node: Node, host: str, port: int):
        self.node = node
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None

    async def start(self) -> None:
        """Start listening for connections."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )
        listen_addr = f"{self.host}:{self.port}"
        if DEBUG >= 1:
            print(f"Socket server started, listening on {listen_addr}")

    async def stop(self) -> None:
        """Stop server and close all connections."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            if DEBUG >= 1:
                print("Socket server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming client connection."""
        peer_addr = writer.get_extra_info('peername')
        if DEBUG >= 2:
            print(f"New connection from {peer_addr}")

        try:
            while True:
                # Read message header
                try:
                    header = await reader.readexactly(HEADER_SIZE)
                except asyncio.IncompleteReadError:
                    # Connection closed
                    break

                msg_type, payload_len = unpack_header(header)

                # Read payload
                payload = await reader.readexactly(payload_len)

                # Handle message based on type
                response = await self._process_message(msg_type, payload)

                # Send response if any
                if response is not None:
                    response_type, response_payload = response
                    message = pack_message(response_type, response_payload)
                    writer.write(message)
                    await writer.drain()

        except Exception as e:
            if DEBUG >= 2:
                print(f"Error handling client {peer_addr}: {e}")
                import traceback
                traceback.print_exc()
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            if DEBUG >= 2:
                print(f"Connection closed: {peer_addr}")

    async def _process_message(
        self,
        msg_type: MessageType,
        payload: bytes
    ) -> Optional[tuple[MessageType, bytes]]:
        """
        Process incoming message and return response.

        Returns:
            (response_type, response_payload) or None if no response
        """
        try:
            if msg_type == MessageType.HEALTH_CHECK_REQUEST:
                return await self._handle_health_check(payload)

            elif msg_type == MessageType.SEND_PROMPT_REQUEST:
                return await self._handle_send_prompt(payload)

            elif msg_type == MessageType.SEND_TENSOR_REQUEST:
                return await self._handle_send_tensor(payload)

            elif msg_type == MessageType.COLLECT_TOPOLOGY_REQUEST:
                return await self._handle_collect_topology(payload)

            elif msg_type == MessageType.SEND_RESULT:
                await self._handle_send_result(payload)
                return None  # No response

            elif msg_type == MessageType.SEND_OPAQUE_STATUS:
                await self._handle_send_opaque_status(payload)
                return None  # No response

            else:
                if DEBUG >= 2:
                    print(f"Unknown message type: {msg_type}")
                return None

        except Exception as e:
            if DEBUG >= 2:
                print(f"Error processing message type {msg_type}: {e}")
                import traceback
                traceback.print_exc()
            return None

    async def _handle_health_check(self, payload: bytes) -> tuple[MessageType, bytes]:
        """Handle health check request."""
        response = encode_health_check_response(True)
        return MessageType.HEALTH_CHECK_RESPONSE, response

    async def _handle_send_prompt(self, payload: bytes) -> Optional[tuple[MessageType, bytes]]:
        """Handle send_prompt request."""
        data = decode_send_prompt_request(payload)

        shard_data = data['shard']
        shard = Shard(
            model_id=shard_data['model_id'],
            start_layer=shard_data['start_layer'],
            end_layer=shard_data['end_layer'],
            n_layers=shard_data['n_layers'],
        )

        prompt = data['prompt']
        request_id = data.get('request_id')
        inference_state = data.get('inference_state')

        result = await self.node.process_prompt(shard, prompt, request_id, inference_state)

        if DEBUG >= 5:
            print(f"SendPrompt {shard=} {prompt=} {request_id=} result: {result}")

        # For prompt requests, we don't return the tensor immediately
        # Results are sent via send_result callbacks
        return None

    async def _handle_send_tensor(self, payload: bytes) -> tuple[MessageType, bytes]:
        """Handle send_tensor request."""
        metadata, tensor_data = decode_send_tensor_request(payload)

        shard_data = metadata['shard']
        shard = Shard(
            model_id=shard_data['model_id'],
            start_layer=shard_data['start_layer'],
            end_layer=shard_data['end_layer'],
            n_layers=shard_data['n_layers'],
        )

        # Deserialize tensor
        tensor_meta = metadata['tensor']
        tensor = array_from_bytes(
            tensor_data,
            tuple(tensor_meta['shape']),
            tensor_meta['dtype']
        )

        request_id = metadata.get('request_id')
        inference_state = metadata.get('inference_state')

        result = await self.node.process_tensor(shard, tensor, request_id, inference_state)

        if DEBUG >= 5:
            print(f"SendTensor {shard=} {tensor=} {request_id=} result: {result}")

        # Encode response
        if result is not None:
            tensor_bytes = result.tobytes()
            response = encode_send_tensor_response(
                tensor_bytes,
                result.shape,
                str(result.dtype)
            )
        else:
            response = encode_send_tensor_response(None, None, None)

        return MessageType.SEND_TENSOR_RESPONSE, response

    async def _handle_collect_topology(self, payload: bytes) -> tuple[MessageType, bytes]:
        """Handle collect_topology request."""
        data = decode_collect_topology_request(payload)
        max_depth = data['max_depth']
        visited = set(data['visited'])

        topology = self.node.current_topology

        # Serialize topology
        nodes = {
            node_id: {
                'model': cap.model,
                'chip': cap.chip,
                'memory': cap.memory,
                'flops': {
                    'fp32': cap.flops.fp32,
                    'fp16': cap.flops.fp16,
                    'int8': cap.flops.int8,
                }
            }
            for node_id, cap in topology.nodes.items()
        }

        peer_graph = {
            node_id: [
                {'to_id': conn.to_id, 'description': conn.description}
                for conn in connections
            ]
            for node_id, connections in topology.peer_graph.items()
        }

        if DEBUG >= 5:
            print(f"CollectTopology {max_depth=} {visited=} {nodes=} {peer_graph=}")

        response = encode_collect_topology_response(nodes, peer_graph)
        return MessageType.COLLECT_TOPOLOGY_RESPONSE, response

    async def _handle_send_result(self, payload: bytes) -> None:
        """Handle send_result request."""
        data = decode_send_result(payload)

        request_id = data['request_id']
        result = data['result']
        is_finished = data['is_finished']

        # Handle tensor results
        if 'tensor_data' in data:
            tensor_meta = data['tensor']
            result = np.frombuffer(
                data['tensor_data'],
                dtype=tensor_meta['dtype']
            ).reshape(tensor_meta['shape'])

        if DEBUG >= 5:
            print(f"Received SendResult: {request_id=} {result=} {is_finished=}")

        # Trigger callback
        self.node.on_token.trigger_all(request_id, result, is_finished)

    async def _handle_send_opaque_status(self, payload: bytes) -> None:
        """Handle send_opaque_status request."""
        data = decode_send_opaque_status(payload)

        request_id = data['request_id']
        status = data['status']

        if DEBUG >= 8:
            print(f"Received SendOpaqueStatus: {request_id=} {status=}")

        # Trigger callback
        self.node.on_opaque_status.trigger_all(request_id, status)
