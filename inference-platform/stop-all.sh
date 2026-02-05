#!/bin/bash
# Stop all inference services

set -e

echo "Stopping Gateway and Nginx..."
docker compose -f docker-compose.gateway.yml down

echo "Stopping Chat service..."
docker compose -f docker-compose.chat.yml down

echo "Stopping Text2SQL service..."
docker compose -f docker-compose.text2sql.yml down

echo ""
echo "All services stopped successfully!"
