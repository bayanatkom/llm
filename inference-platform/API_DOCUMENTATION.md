# LLM Inference Platform - API Documentation

## ✅ System Status

### GPU Configuration
- **GPU 0**: NVIDIA L4 (23 GB) - Running Snowflake Arctic-Text2SQL-R1-7B
- **GPU 1**: NVIDIA L4 (23 GB) - Running Qwen 2.5 7B Instruct
- **Status**: Both models successfully deployed and running on dedicated GPUs

### Services Running
```
✅ vllm-text2sql  - Port 8000 (GPU 0)
✅ vllm-chat      - Port 8000 (GPU 1) 
✅ inference-nginx - Ports 80, 443
```

### Performance Specs
- **Max Context Length**: 8,192 tokens
- **Concurrent Capacity**: ~5-6 requests @ 16K context per GPU
- **GPU Memory Usage**: ~15 GB per model
- **Available KV Cache**: ~5.17 GB per GPU

---

## API Endpoints

### Base URL
```
https://llm.bayanatkom.com
```

### Authentication
All requests require Bearer token authentication:
```
Authorization: Bearer <API_KEY>
```

**API Keys:**
- **Public Gateway Key**: `4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8`
- **Backend Direct Access**: `b0a9c79d1e545f7a0fac2805927d0c55e8031544f6344ad3daf5c6c995c57fc6`

---

## 1. Chat Completions (Qwen 2.5 7B)

### Endpoint
```
POST https://llm.bayanatkom.com/v1/chat/completions
```

### Request Format
```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "max_tokens": 100,
  "temperature": 0.7,
  "top_p": 0.9,
  "stream": false
}
```

### cURL Example
```bash
curl -X POST https://llm.bayanatkom.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
      {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    "max_tokens": 150
  }'
```

### Response Format
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1770292152,
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Quantum computing uses..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 45,
    "total_tokens": 60
  }
}
```

### Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| model | string | required | Must be "Qwen/Qwen2.5-7B-Instruct" |
| messages | array | required | Conversation history |
| max_tokens | integer | 2048 | Maximum tokens to generate |
| temperature | float | 0.7 | Sampling temperature (0-2) |
| top_p | float | 1.0 | Nucleus sampling threshold |
| stream | boolean | false | Enable streaming responses |

---

## 2. Text2SQL (Snowflake Arctic)

### Endpoint  
```
POST https://llm.bayanatkom.com/text2sql
```

### Request Format
```json
{
  "model": "Snowflake/Arctic-Text2SQL-R1-7B",
  "messages": [
    {"role": "user", "content": "Convert to SQL: Show all users who registered in the last 30 days"}
  ],
  "max_tokens": 200
}
```

### cURL Example
```bash
curl -X POST https://llm.bayanatkom.com/text2sql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8" \
  -d '{
    "model": "Snowflake/Arctic-Text2SQL-R1-7B",
    "messages": [
      {"role": "user", "content": "Convert to SQL: Get top 10 customers by revenue"}
    ],
    "max_tokens": 150
  }'
```

---

## Direct Backend Access (For Testing)

When gateway has issues, you can access backends directly from the server:

### Chat Backend (GPU 1)
```bash
docker run --rm --network inference-network curlimages/curl:latest \
  curl -X POST http://chat:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer b0a9c79d1e545f7a0fac2805927d0c55e8031544f6344ad3daf5c6c995c57fc6" \
  -d '{"model": "Qwen/Qwen2.5-7B-Instruct", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 50}'
```

### Text2SQL Backend (GPU 0)
```bash
docker run --rm --network inference-network curlimages/curl:latest \
  curl -X POST http://text2sql:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer b0a9c79d1e545f7a0fac2805927d0c55e8031544f6344ad3daf5c6c995c57fc6" \
  -d '{"model": "Snowflake/Arctic-Text2SQL-R1-7B", "messages": [{"role": "user", "content": "SQL query"}], "max_tokens": 100}'
```

---

## Health Checks

### Gateway Health
```bash
curl -k https://llm.bayanatkom.com/health
```

**Response:**
```json
{
  "status": "healthy",
  "backends": {
    "chat": ["http://chat:8000"],
    "text2sql": ["http://text2sql:8000"]
  }
}
```

### Individual Backend Health
```bash
# Chat backend
curl http://chat:8000/health \
  -H "Authorization: Bearer b0a9c79d1e545f7a0fac2805927d0c55e8031544f6344ad3daf5c6c995c57fc6"

# Text2SQL backend  
curl http://text2sql:8000/health \
  -H "Authorization: Bearer b0a9c79d1e545f7a0fac2805927d0c55e8031544f6344ad3daf5c6c995c57fc6"
```

---

## Rate Limits & Quotas

| Limit Type | Value |
|------------|-------|
| Requests per second | 50 per IP |
| Concurrent requests | 5-6 @ 16K context |
| Daily tokens | 10M per organization |
| Daily requests | 100K per organization |
| Monthly tokens | 300M per organization |

---

## Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 401 | Unauthorized | Check API key |
| 429 | Rate limit exceeded | Retry with backoff |
| 503 | No healthy backends | Wait for backends to recover |
| 504 | Gateway timeout | Request too complex or slow |

---

## Streaming Responses

Enable streaming for real-time token generation:

```bash
curl -X POST https://llm.bayanatkom.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "max_tokens": 200,
    "stream": true
  }' \
  --no-buffer
```

Stream format (Server-Sent Events):
```
data: {"choices":[{"delta":{"content":"Once"}}]}
data: {"choices":[{"delta":{"content":" upon"}}]}
data: [DONE]
```

---

## Management Commands

### Start All Services
```bash
cd /opt/llm/inference-platform
./start-all.sh
```

### Stop All Services
```bash
cd /opt/llm/inference-platform
./stop-all.sh
```

### Check GPU Usage
```bash
nvidia-smi
```

### View Logs
```bash
docker logs vllm-chat -f
docker logs vllm-text2sql -f
docker logs inference-gateway -f
```

---

## Notes

1. **Context Length**: Currently set to 8,192 tokens. Can be increased to 16,384 with reduced concurrency.

2. **GPU Isolation**: Each model runs on dedicated GPU with proper CUDA device isolation via separate docker-compose files.

3. **No Triton Errors**: Successfully using FLASH_ATTN backend instead of Triton.

4. **Capacity Planning**: For 10 concurrent requests @ 16K context, consider using 4-bit quantization or upgrading to A100 GPUs.
