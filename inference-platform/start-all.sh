#!/bin/bash
# Start all inference services in correct order

set -e

echo "Starting Text2SQL service on GPU 0..."
docker compose -f docker-compose.text2sql.yml up -d

echo "Starting Chat service on GPU 1..."
docker compose -f docker-compose.chat.yml up -d

echo "Starting Gateway and Nginx..."
docker compose -f docker-compose.gateway.yml up -d

echo ""
echo "All services started successfully!"
echo ""
echo "Checking GPU utilization..."
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv
echo ""
echo "Container status:"
docker ps --filter "name=vllm\|inference-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
