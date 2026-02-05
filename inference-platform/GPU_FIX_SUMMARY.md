# GPU Issues - FIXED ✅

## Problems Fixed

### 1. ✅ GPU Access Issue (SOLVED)
**Problem**: Triton errors indicating no GPU access
**Root Cause**: Docker Compose `deploy.resources.reservations` with `device_ids` was being ignored
**Solution**: Created separate docker-compose files per model with proper GPU device assignment

### 2. ✅ Model Name Issue (SOLVED)
**Problem**: Invalid model name `Snowflake/Arctic-R1-7B` 
**Correct Name**: `Snowflake/Arctic-Text2SQL-R1-7B`

### 3. ✅ GPU Isolation Issue (SOLVED)
**Problem**: Both containers could see both GPUs, causing memory conflicts
**Solution**: Separate compose files ensure proper isolation:
- `docker-compose.text2sql.yml` - Snowflake Arctic on GPU 0
- `docker-compose.chat.yml` - Qwen 2.5 7B on GPU 1
- `docker-compose.gateway.yml` - Gateway and Nginx

## Current Status

### GPU Utilization
```
GPU 0: 14.9 GB / 23 GB (Snowflake Arctic-Text2SQL-R1-7B)
GPU 1: 14.9 GB / 23 GB (Qwen 2.5 7B Instruct)
```

### Services Running
- ✅ vllm-text2sql (GPU 0)
- ✅ vllm-chat (GPU 1)
- ✅ inference-gateway
- ✅ inference-nginx

### No More Triton Errors
Both models using FLASH_ATTN backend successfully.

## Usage

### Start All Services
```bash
cd inference-platform
./start-all.sh
```

### Stop All Services
```bash
cd inference-platform
./stop-all.sh
```

### Manual Management
```bash
# Start individual services
docker compose -f docker-compose.text2sql.yml up -d
docker compose -f docker-compose.chat.yml up -d
docker compose -f docker-compose.gateway.yml up -d

# Stop individual services
docker compose -f docker-compose.gateway.yml down
docker compose -f docker-compose.chat.yml down
docker compose -f docker-compose.text2sql.yml down
```

## ⚠️ IMPORTANT: Capacity Limitation Discovered

**Current Configuration:**
- Max context: 8,192 tokens
- KV cache: 5.17 GB per GPU
- **Concurrent capacity: ~11 requests @ 8K tokens**

**Your Stated Requirement:**
- 10 concurrent × 32K tokens = **DOES NOT FIT on L4 GPUs**

See `CAPACITY_ANALYSIS.md` for solutions:
1. Upgrade to A100 GPUs
2. Use 4-bit quantization (recommended for L4)
3. Reduce context length or concurrent load

## Why Separate Docker Compose Files?

This approach ensures:
1. **True GPU isolation** - Each model sees only its assigned GPU
2. **Independent scaling** - Start/stop models independently
3. **Clear resource allocation** - No ambiguity about which GPU serves which model
4. **Production best practice** - Easier to manage and debug
