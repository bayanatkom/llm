# LLM API Configuration Guide

## Quick Reference

| Setting | Value |
|---------|-------|
| **API Base URL** | `https://llm.bayanatkom.com` |
| **API Key** | `4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8` |
| **API Version** | `v1` |
| **Models Endpoint** | `https://llm.bayanatkom.com/v1/models` |
| **Compatibility** | OpenAI-compatible, OpenRouter-compatible |

---

## Available Models

### 1. General Chat Model (Qwen 2.5 7B Instruct)

| Setting | Value |
|---------|-------|
| **Model ID (OpenRouter-style)** | `qwen/qwen-2.5-7b-instruct` |
| **Model ID (HuggingFace-style)** | `Qwen/Qwen2.5-7B-Instruct` |
| **Endpoint** | `https://llm.bayanatkom.com/v1/chat/completions` |
| **Context Length** | `8192` |
| **Max Output Tokens** | `4096` |
| **Type** | Chat Completion |

### 2. Text-to-SQL Model (Arctic Text2SQL R1 7B)

| Setting | Value |
|---------|-------|
| **Model ID (OpenRouter-style)** | `snowflake/arctic-text2sql-r1-7b` |
| **Model ID (HuggingFace-style)** | `Snowflake/Arctic-Text2SQL-R1-7B` |
| **Endpoint** | `https://llm.bayanatkom.com/v1/completions` |
| **Context Length** | `8192` |
| **Max Output Tokens** | `4096` |
| **Type** | Text Completion |

---

## OpenRouter Configuration

This API is **fully OpenRouter-compatible**. The `/v1/models` endpoint returns OpenRouter's schema format with:
- `canonical_slug` - Normalized model identifier
- `name` - Human-readable model name
- `description` - Model description
- `context_length` - Maximum context window
- `architecture` - Input/output modalities and tokenizer info
- `pricing` - Pricing information (free for this deployment)
- `supported_parameters` - List of supported API parameters

### Using with OpenRouter-compatible Clients

```
API Base:       https://llm.bayanatkom.com/v1
API Key:        4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8
Provider Name:  Openrouter (or custom)

Model IDs:
  - qwen/qwen-2.5-7b-instruct       (Chat)
  - snowflake/arctic-text2sql-r1-7b (Text2SQL)
```

---

## LiteLLM Configuration

For LiteLLM-compatible systems, use these values:

### Option 1: Chat Model Configuration

```
API Key:        4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8
API Base:       https://llm.bayanatkom.com
API Version:    v1

Model Configurations:
  - Model Name:       Qwen/Qwen2.5-7B-Instruct
  - Max Input Tokens: 8192

Default Model: Qwen/Qwen2.5-7B-Instruct
```

### Option 2: Text2SQL Model Configuration

```
API Key:        4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8
API Base:       https://llm.bayanatkom.com
API Version:    v1

Model Configurations:
  - Model Name:       Snowflake/Arctic-Text2SQL-R1-7B
  - Max Input Tokens: 8192

Default Model: Snowflake/Arctic-Text2SQL-R1-7B
```

---

## Example API Calls

### List Available Models

```bash
curl https://llm.bayanatkom.com/v1/models \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8"
```

### Chat Completion (OpenRouter-style model ID)

```bash
curl -X POST https://llm.bayanatkom.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8" \
  -d '{
    "model": "qwen/qwen-2.5-7b-instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Chat Completion (HuggingFace-style model ID)

```bash
curl -X POST https://llm.bayanatkom.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

### Text Completion (Text2SQL)

```bash
curl -X POST https://llm.bayanatkom.com/v1/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 4957a0d56333b448ef02b9546d5286969a3586cec917c638164c5790191fe9f8" \
  -d '{
    "model": "snowflake/arctic-text2sql-r1-7b",
    "prompt": "Convert to SQL: Show all users who registered in 2024",
    "max_tokens": 256,
    "temperature": 0.1
  }'
```

---

## Supported Parameters

### Chat Completions (`/v1/chat/completions`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | required | Model name |
| `messages` | array | required | Array of messages with `role` and `content` |
| `max_tokens` | integer | 2048 | Maximum tokens to generate |
| `temperature` | float | 0.7 | Sampling temperature (0.0-2.0) |
| `top_p` | float | 0.9 | Nucleus sampling parameter |
| `stream` | boolean | false | Enable streaming response |

### Text Completions (`/v1/completions`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | required | Model name |
| `prompt` | string | required | Text prompt |
| `max_tokens` | integer | 2048 | Maximum tokens to generate |
| `temperature` | float | 0.7 | Sampling temperature (0.0-2.0) |
| `top_p` | float | 0.9 | Nucleus sampling parameter |
| `stream` | boolean | false | Enable streaming response |

---

## Rate Limits

| Limit Type | Value |
|------------|-------|
| Requests per second per IP | 10 |
| Burst requests | 50 |
| Max concurrent requests per IP | 20 |
| Request timeout | 600 seconds |
| Max request body size | 50 MB |

---

## Response Format

### Chat Completion Response

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Response text..."
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

---

## Support

For technical support or API key issues, contact: **support@bayanatkom.com**
