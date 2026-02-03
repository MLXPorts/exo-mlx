#!/bin/bash
# Test script for local socket-based peer communication

# Create config for node 1 (pointing to node 2)
cat > /tmp/peer_config_node1.json << 'EOF'
{
  "peers": {
    "test-node-2": {
      "address": "127.0.0.1:50052",
      "device_capabilities": {
        "model": "Test Node 2",
        "chip": "Apple M3",
        "memory": 32768,
        "flops": {
          "fp32": 10.0,
          "fp16": 20.0,
          "int8": 40.0
        }
      }
    }
  }
}
EOF

# Create config for node 2 (pointing to node 1)
cat > /tmp/peer_config_node2.json << 'EOF'
{
  "peers": {
    "test-node-1": {
      "address": "127.0.0.1:50051",
      "device_capabilities": {
        "model": "Test Node 1",
        "chip": "Apple M3",
        "memory": 32768,
        "flops": {
          "fp32": 10.0,
          "fp16": 20.0,
          "int8": 40.0
        }
      }
    }
  }
}
EOF

echo "Starting Node 1 on port 50051..."
python -m exo.main run \
  --node-id test-node-1 \
  --node-port 50051 \
  --chatgpt-api-port 52415 \
  --discovery-module manual \
  --discovery-config-path /tmp/peer_config_node1.json \
  --disable-tui &

NODE1_PID=$!
sleep 5

echo "Starting Node 2 on port 50052..."
python -m exo.main run \
  --node-id test-node-2 \
  --node-port 50052 \
  --chatgpt-api-port 52416 \
  --discovery-module manual \
  --discovery-config-path /tmp/peer_config_node2.json \
  --disable-tui &

NODE2_PID=$!

echo ""
echo "================================"
echo "Nodes started!"
echo "Node 1 PID: $NODE1_PID (port 50051, API 52415)"
echo "Node 2 PID: $NODE2_PID (port 50052, API 52416)"
echo "================================"
echo ""
echo "To test the connection:"
echo "  curl http://localhost:52415/health"
echo "  curl http://localhost:52416/health"
echo ""
echo "To stop:"
echo "  kill $NODE1_PID $NODE2_PID"
echo ""
echo "Logs will appear below..."
echo ""

# Wait for interrupt
trap "kill $NODE1_PID $NODE2_PID 2>/dev/null; exit" INT TERM
wait
