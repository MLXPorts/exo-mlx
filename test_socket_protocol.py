#!/usr/bin/env python
"""
Simple test for socket-based protocol without full node setup.
Tests basic message encoding/decoding and socket communication.
"""

import asyncio
import sys
from exo.networking.socket.protocol import (
    MessageType,
    pack_message, unpack_header,
    encode_health_check_request, decode_health_check_response,
    encode_health_check_response,
    encode_send_tensor_request, decode_send_tensor_request,
    encode_send_tensor_response, decode_send_tensor_response,
    encode_shard,
)
import numpy as np


async def test_protocol_encoding():
    """Test message encoding/decoding."""
    print("Testing protocol encoding/decoding...")

    # Test 1: Health check
    print("  1. Health check message...")
    req_payload = encode_health_check_request()
    req_msg = pack_message(MessageType.HEALTH_CHECK_REQUEST, req_payload)

    msg_type, payload_len = unpack_header(req_msg[:9])
    assert msg_type == MessageType.HEALTH_CHECK_REQUEST
    print("     ✓ Health check request encoding/decoding works")

    # Test 2: Health check response
    resp_payload = encode_health_check_response(True)
    resp_msg = pack_message(MessageType.HEALTH_CHECK_RESPONSE, resp_payload)

    msg_type, payload_len = unpack_header(resp_msg[:9])
    assert msg_type == MessageType.HEALTH_CHECK_RESPONSE
    is_healthy = decode_health_check_response(resp_msg[9:])
    assert is_healthy == True
    print("     ✓ Health check response encoding/decoding works")

    # Test 3: Tensor message
    print("  2. Tensor message...")
    shard = encode_shard("test-model", 0, 10, 32)
    test_array = np.random.randn(10, 20).astype(np.float32)
    tensor_bytes = test_array.tobytes()

    tensor_payload = encode_send_tensor_request(
        shard,
        tensor_bytes,
        test_array.shape,
        str(test_array.dtype),
        "test-request-123"
    )
    tensor_msg = pack_message(MessageType.SEND_TENSOR_REQUEST, tensor_payload)

    msg_type, payload_len = unpack_header(tensor_msg[:9])
    assert msg_type == MessageType.SEND_TENSOR_REQUEST

    metadata, decoded_tensor = decode_send_tensor_request(tensor_msg[9:])
    assert metadata['request_id'] == "test-request-123"
    assert metadata['tensor']['shape'] == [10, 20]

    reconstructed = np.frombuffer(decoded_tensor, dtype=np.float32).reshape((10, 20))
    assert np.allclose(reconstructed, test_array)
    print("     ✓ Tensor message encoding/decoding works")

    print("\n✅ All protocol tests passed!\n")


async def test_socket_connection():
    """Test basic socket server/client connection."""
    print("Testing socket server/client connection...")

    # Simple echo server
    async def handle_client(reader, writer):
        try:
            # Read header
            header = await reader.readexactly(9)
            msg_type, payload_len = unpack_header(header)

            # Read payload
            payload = await reader.readexactly(payload_len)

            print(f"  Server received: {msg_type}")

            # Echo back a health check response
            response = pack_message(
                MessageType.HEALTH_CHECK_RESPONSE,
                encode_health_check_response(True)
            )
            writer.write(response)
            await writer.drain()

        finally:
            writer.close()
            await writer.wait_closed()

    # Start server
    server = await asyncio.start_server(handle_client, '127.0.0.1', 50099)
    print(f"  Server listening on 127.0.0.1:50099")

    # Give server time to start
    await asyncio.sleep(0.1)

    # Connect client
    reader, writer = await asyncio.open_connection('127.0.0.1', 50099)
    print(f"  Client connected")

    # Send health check
    request = pack_message(
        MessageType.HEALTH_CHECK_REQUEST,
        encode_health_check_request()
    )
    writer.write(request)
    await writer.drain()
    print(f"  Client sent health check request")

    # Read response
    header = await reader.readexactly(9)
    msg_type, payload_len = unpack_header(header)
    payload = await reader.readexactly(payload_len)

    assert msg_type == MessageType.HEALTH_CHECK_RESPONSE
    is_healthy = decode_health_check_response(payload)
    assert is_healthy == True
    print(f"  Client received response: healthy={is_healthy}")

    # Cleanup
    writer.close()
    await writer.wait_closed()
    server.close()
    await server.wait_closed()

    print("\n✅ Socket connection test passed!\n")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Socket Protocol Test Suite")
    print("="*60 + "\n")

    try:
        await test_protocol_encoding()
        await test_socket_connection()

        print("="*60)
        print("🎉 All tests passed!")
        print("="*60 + "\n")
        return 0

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
