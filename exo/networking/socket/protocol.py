#!/usr/bin/env python
"""
Binary protocol for peer-to-peer communication over raw sockets.

Message Format:
  [4 bytes: magic header b'EXO\x01']
  [1 byte: message type]
  [4 bytes: message length (big-endian)]
  [N bytes: message payload]

This protocol is designed for:
- Maximum speed for tensor transfers
- SSH tunnel compatibility
- Simple connection management
"""

import struct
from enum import IntEnum
from typing import Optional, Dict, List, Tuple
import json

# Protocol constants
MAGIC_HEADER = b'EXO\x01'
HEADER_SIZE = len(MAGIC_HEADER) + 1 + 4  # magic + type + length = 9 bytes


class MessageType(IntEnum):
    """Message type identifiers."""
    # Health checks
    HEALTH_CHECK_REQUEST = 0x01
    HEALTH_CHECK_RESPONSE = 0x02

    # Prompt operations
    SEND_PROMPT_REQUEST = 0x10
    SEND_PROMPT_RESPONSE = 0x11

    # Tensor operations
    SEND_TENSOR_REQUEST = 0x12
    SEND_TENSOR_RESPONSE = 0x13

    # Training operations
    SEND_EXAMPLE_REQUEST = 0x14
    SEND_EXAMPLE_RESPONSE = 0x15

    # Results
    SEND_RESULT = 0x20

    # Topology
    COLLECT_TOPOLOGY_REQUEST = 0x30
    COLLECT_TOPOLOGY_RESPONSE = 0x31

    # Status
    SEND_OPAQUE_STATUS = 0x40


def pack_message(msg_type: MessageType, payload: bytes) -> bytes:
    """
    Pack a message with header.

    Args:
        msg_type: Message type
        payload: Raw payload bytes

    Returns:
        Full message with header
    """
    header = MAGIC_HEADER
    header += struct.pack('B', msg_type)
    header += struct.pack('>I', len(payload))
    return header + payload


def unpack_header(header: bytes) -> Tuple[MessageType, int]:
    """
    Unpack message header.

    Args:
        header: 9-byte header

    Returns:
        (message_type, payload_length)

    Raises:
        ValueError: If magic header is invalid
    """
    if len(header) != HEADER_SIZE:
        raise ValueError(f"Invalid header size: {len(header)}, expected {HEADER_SIZE}")

    magic = header[:4]
    if magic != MAGIC_HEADER:
        raise ValueError(f"Invalid magic header: {magic!r}")

    msg_type = MessageType(struct.unpack('B', header[4:5])[0])
    payload_len = struct.unpack('>I', header[5:9])[0]

    return msg_type, payload_len


def encode_json(data: dict) -> bytes:
    """Encode dict as JSON bytes."""
    return json.dumps(data).encode('utf-8')


def decode_json(data: bytes) -> dict:
    """Decode JSON bytes to dict."""
    return json.loads(data.decode('utf-8'))


# Payload encoding helpers

def encode_health_check_request() -> bytes:
    """Encode health check request (empty payload)."""
    return b''


def encode_health_check_response(is_healthy: bool) -> bytes:
    """Encode health check response."""
    return encode_json({"is_healthy": is_healthy})


def decode_health_check_response(payload: bytes) -> bool:
    """Decode health check response."""
    return decode_json(payload)["is_healthy"]


def encode_shard(model_id: str, start_layer: int, end_layer: int, n_layers: int) -> dict:
    """Encode shard metadata."""
    return {
        "model_id": model_id,
        "start_layer": start_layer,
        "end_layer": end_layer,
        "n_layers": n_layers,
    }


def decode_shard(data: dict) -> dict:
    """Decode shard metadata."""
    return {
        "model_id": data["model_id"],
        "start_layer": data["start_layer"],
        "end_layer": data["end_layer"],
        "n_layers": data["n_layers"],
    }


def encode_tensor_metadata(shape: tuple, dtype: str) -> dict:
    """Encode tensor metadata."""
    return {
        "shape": list(shape),
        "dtype": dtype,
    }


def encode_send_prompt_request(
    shard: dict,
    prompt: str,
    request_id: Optional[str] = None,
    inference_state: Optional[dict] = None
) -> bytes:
    """Encode send_prompt request."""
    data = {
        "shard": shard,
        "prompt": prompt,
        "request_id": request_id,
        "inference_state": inference_state,
    }
    return encode_json(data)


def decode_send_prompt_request(payload: bytes) -> dict:
    """Decode send_prompt request."""
    return decode_json(payload)


def encode_send_tensor_request(
    shard: dict,
    tensor_data: bytes,
    shape: tuple,
    dtype: str,
    request_id: Optional[str] = None,
    inference_state: Optional[dict] = None
) -> bytes:
    """
    Encode send_tensor request.

    Format:
        [4 bytes: metadata_len (big-endian)]
        [N bytes: JSON metadata]
        [M bytes: tensor binary data]
    """
    metadata = {
        "shard": shard,
        "tensor": encode_tensor_metadata(shape, dtype),
        "request_id": request_id,
        "inference_state": inference_state,
    }
    metadata_bytes = encode_json(metadata)
    metadata_len = struct.pack('>I', len(metadata_bytes))

    return metadata_len + metadata_bytes + tensor_data


def decode_send_tensor_request(payload: bytes) -> Tuple[dict, bytes]:
    """
    Decode send_tensor request.

    Returns:
        (metadata_dict, tensor_bytes)
    """
    metadata_len = struct.unpack('>I', payload[:4])[0]
    metadata = decode_json(payload[4:4+metadata_len])
    tensor_data = payload[4+metadata_len:]
    return metadata, tensor_data


def encode_send_tensor_response(
    tensor_data: Optional[bytes],
    shape: Optional[tuple],
    dtype: Optional[str]
) -> bytes:
    """
    Encode send_tensor response.

    Format: same as request
    """
    if tensor_data is None or shape is None or dtype is None:
        # Empty response
        return struct.pack('>I', 0)

    metadata = encode_tensor_metadata(shape, dtype)
    metadata_bytes = encode_json(metadata)
    metadata_len = struct.pack('>I', len(metadata_bytes))

    return metadata_len + metadata_bytes + tensor_data


def decode_send_tensor_response(payload: bytes) -> Optional[Tuple[dict, bytes]]:
    """
    Decode send_tensor response.

    Returns:
        (metadata_dict, tensor_bytes) or None if empty
    """
    if len(payload) < 4:
        return None

    metadata_len = struct.unpack('>I', payload[:4])[0]
    if metadata_len == 0:
        return None

    metadata = decode_json(payload[4:4+metadata_len])
    tensor_data = payload[4+metadata_len:]
    return metadata, tensor_data


def encode_send_result(
    request_id: str,
    result: List[int],
    is_finished: bool,
    tensor_data: Optional[bytes] = None,
    shape: Optional[tuple] = None,
    dtype: Optional[str] = None
) -> bytes:
    """Encode send_result request."""
    data = {
        "request_id": request_id,
        "result": result,
        "is_finished": is_finished,
    }

    if tensor_data is not None:
        data["tensor"] = encode_tensor_metadata(shape, dtype)
        metadata_bytes = encode_json(data)
        metadata_len = struct.pack('>I', len(metadata_bytes))
        return metadata_len + metadata_bytes + tensor_data
    else:
        return encode_json(data)


def decode_send_result(payload: bytes) -> dict:
    """Decode send_result request."""
    # Check if there's a length prefix (indicates tensor data)
    if len(payload) >= 4:
        try:
            metadata_len = struct.unpack('>I', payload[:4])[0]
            if metadata_len > 0 and metadata_len < len(payload):
                metadata = decode_json(payload[4:4+metadata_len])
                if "tensor" in metadata:
                    metadata["tensor_data"] = payload[4+metadata_len:]
                    return metadata
        except:
            pass

    # No tensor data, just JSON
    return decode_json(payload)


def encode_collect_topology_request(visited: set, max_depth: int) -> bytes:
    """Encode collect_topology request."""
    data = {
        "visited": list(visited),
        "max_depth": max_depth,
    }
    return encode_json(data)


def decode_collect_topology_request(payload: bytes) -> dict:
    """Decode collect_topology request."""
    return decode_json(payload)


def encode_collect_topology_response(nodes: dict, peer_graph: dict) -> bytes:
    """Encode collect_topology response."""
    data = {
        "nodes": nodes,
        "peer_graph": peer_graph,
    }
    return encode_json(data)


def decode_collect_topology_response(payload: bytes) -> dict:
    """Decode collect_topology response."""
    return decode_json(payload)


def encode_send_opaque_status(request_id: str, status: str) -> bytes:
    """Encode send_opaque_status request."""
    data = {
        "request_id": request_id,
        "status": status,
    }
    return encode_json(data)


def decode_send_opaque_status(payload: bytes) -> dict:
    """Decode send_opaque_status request."""
    return decode_json(payload)
