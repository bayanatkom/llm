# Enterprise-Grade LLM Inference Platform

Production-ready inference platform running on 4×L4 GPUs with comprehensive observability, resilience, and resource management.

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- NVIDIA GPU drivers
- NVIDIA Container Toolkit
- 4× L4 GPUs (24GB each)
- SSL certificates (for HTTPS)

### Initial Setup

```bash
# 1. Clone and navigate
cd inference-platform

# 2. Create environment file
cp .env.example .env

# 3. Edit .env with your API keys
nano .env
# Set GATEWAY_API_KEY and BACKEND_API_KEY

# 4. Create HuggingFace cache directory
mkdir -p hf-cache

# 5. SSL certificates are already configured
# The platform uses certificates from ../ssl_certificate/
# - cert-fullchain.crt (certificate chain)
# - cert.key (private key)

# 6. Start the platform
docker compose up -d --build

# 7. Start monitoring (optional but recommended)
docker compose -f docker-compose.monitoring.yml up -d

# 8. Verify all services are running
docker compose ps
```

## 📊 Architecture

### GPU Allocation
- **GPU 0**: Qwen2.5-7B-Instruct (chat0) - Load-balanced
- **GPU 1**: Qwen2.5-7B-Instruct (chat1) - Load-balanced
- **GPU 2**: Arctic-Text2SQL-7B - Dedicated endpoint
- **GPU 3**: Snowflake-arctic-embed-l-v2.0 + bge-reranker-v2-m3 (shared)

### Components
- **Gateway**: Enterprise FastAPI application with all features
- **vLLM Backends**: 5 model instances across 4 GPUs
- **Nginx**: TLS termination and reverse proxy
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **DCGM Exporter**: GPU metrics

## 🔑 API Endpoints

### Chat Completions (Load-Balanced)
```bash
curl -X POST https://your-host/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7,
    "max_tokens": 2048,
    "stream": false
  }'
```

### Text2SQL
```bash
curl -X POST https://your-host/v1/text2sql \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text2sql",
    "messages": [{"role": "user", "content": "Show all users"}]
  }'
```

### Embeddings
```bash
curl -X POST https://your-host/v1/embeddings \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "snowflake-arctic-embed",
    "input": "Your text here"
  }'
```

### Rerank
```bash
curl -X POST https://your-host/v1/rerank \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-reranker-v2-m3",
    "query": "What is the capital of France?",
    "documents": ["Paris is the capital", "London is a city"]
  }'
```

## 📈 Monitoring

### Access Points
- **Prometheus**: http://your-host:9090
- **Grafana**: http://your-host:3000 (admin/admin)
- **Gateway Metrics**: https://your-host/metrics
- **Health Check**: https://your-host/health/detailed

### Key Metrics
- Request rates, latencies (p50/p95/p99)
- Queue depths and wait times
- Backend health status
- GPU memory and utilization
- Token usage per organization
- Rate limit rejections
- Circuit breaker states

## 🛡️ Enterprise Features

### Observability
- ✅ Prometheus metrics with 20+ custom metrics
- ✅ Structured JSON logging with correlation IDs
- ✅ PII redaction in logs
- ✅ Request/response audit trail

### Resilience
- ✅ Circuit breakers (5 failures → 30s recovery)
- ✅ Retry logic with exponential backoff
- ✅ Active health checks every 10 seconds
- ✅ Graceful shutdown with connection draining
- ✅ Automatic unhealthy backend removal

### Resource Management
- ✅ Per-org rate limiting (50 RPS, burst 100)
- ✅ Per-org concurrency control (120 max)
- ✅ Per-org quotas (10M tokens/day, 100k requests/day)
- ✅ Token counting and tracking
- ✅ Queue admission timeout (2 seconds)

### Performance
- ✅ Response caching (60s TTL, 10k entries)
- ✅ Gzip compression
- ✅ Optimized connection pooling (3000 max, 800 keepalive)
- ✅ Load balancing across chat backends

### Security
- ✅ TLS 1.2/1.3 only
- ✅ Security headers (HSTS, CSP, X-Frame-Options, etc.)
- ✅ API key authentication
- ✅ Request validation
- ✅ Rate limit headers in responses

## ⚙️ Configuration

### Key Environment Variables

```bash
# Rate Limiting
MAX_RPS_PER_IP=50              # Requests per second per org
RPS_BURST=100                  # Burst allowance
MAX_INFLIGHT_PER_IP=120        # Max concurrent requests

# Quotas
ORG_DAILY_TOKEN_LIMIT=10000000      # 10M tokens/day
ORG_DAILY_REQUEST_LIMIT=100000      # 100k requests/day
ORG_MONTHLY_TOKEN_LIMIT=300000000   # 300M tokens/month

# Timeouts
MAX_REQUEST_SECS=5400          # 90 min hard cap
STREAM_IDLE_TIMEOUT_SECS=180   # 3 min idle timeout
QUEUE_TIMEOUT_SECS=2           # Queue admission timeout

# Circuit Breaker
CIRCUIT_FAILURE_THRESHOLD=5    # Failures before opening
CIRCUIT_RECOVERY_TIMEOUT=30    # Seconds before retry
```

See `.env.example` for all configuration options.

## 🔧 Operations

### View Logs
```bash
# Gateway logs
docker logs -f inference-gateway

# All services
docker compose logs -f

# Specific backend
docker logs -f vllm-chat0
```

### Check Health
```bash
# Basic health
curl https://your-host/health

# Detailed health with backend status
curl https://your-host/health/detailed \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"
```

### View Quota Usage
```bash
# Specific organization
curl https://your-host/admin/quota/192.168.1.100 \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"

# All organizations
curl https://your-host/admin/quotas \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"
```

### Restart Services
```bash
# Restart gateway only
docker compose restart gateway

# Restart all
docker compose restart

# Rebuild and restart
docker compose up -d --build
```

### Scale Gateway
```bash
# Edit docker-compose.yml
# Under gateway service, add:
deploy:
  replicas: 3

# Apply changes
docker compose up -d
```

## 📊 GPU Memory Optimization

Current allocation optimized for 24GB L4 GPUs:

```yaml
chat0/chat1:     ~14GB @ 0.90 utilization
text2sql:        ~14GB @ 0.90 utilization
embed + rerank:  ~19GB @ 0.80 utilization (shared GPU)
```

### Tuning Options
```bash
# Adjust GPU memory utilization
--gpu-memory-utilization 0.85  # More conservative
--gpu-memory-utilization 0.95  # More aggressive

# Adjust max model length
--max-model-len 4096   # Reduce for more KV cache headroom
--max-model-len 16384  # Increase for longer contexts

# Enable prefix caching (saves memory for repeated prompts)
--enable-prefix-caching
```

## 🚨 Troubleshooting

### Gateway Won't Start
```bash
# Check logs
docker logs inference-gateway

# Verify environment variables
docker exec inference-gateway env | grep GATEWAY

# Validate configuration
docker exec inference-gateway python -c "from app.config import settings; settings.validate()"
```

### Backend Unhealthy
```bash
# Check backend logs
docker logs vllm-chat0

# Check GPU availability
nvidia-smi

# Verify backend is responding
curl http://localhost:8000/health
```

### High Memory Usage
```bash
# Check GPU memory
nvidia-smi

# Reduce gpu-memory-utilization in docker-compose.yml
# Reduce max-model-len
# Enable prefix caching
```

### Rate Limiting Issues
```bash
# Check current limits
curl https://your-host/admin/quotas \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"

# Adjust in .env
MAX_RPS_PER_IP=100
MAX_INFLIGHT_PER_IP=200

# Restart gateway
docker compose restart gateway
```

## 📚 Additional Documentation

- **Plan-Enterprise.md**: Detailed architecture and features
- **Plan.md**: Original implementation plan
- **Monitoring Setup**: See `monitoring/` directory
- **API Documentation**: https://your-host/docs (auto-generated)

## 🔐 Security Best Practices

1. **Change default API keys** in `.env`
2. **Use strong SSL certificates** (not self-signed in production)
3. **Restrict network access** to gateway only
4. **Enable PII redaction** in logs
5. **Regularly rotate API keys**
6. **Monitor quota usage** for anomalies
7. **Review audit logs** regularly
8. **Keep Docker images updated**

## 📈 Performance Benchmarks

Expected performance on 4×L4 GPUs:

- **Chat**: ~50-100 tokens/sec per GPU
- **Throughput**: ~100-200 requests/sec (with load balancing)
- **Latency**: p50 < 500ms, p95 < 2s (excluding generation time)
- **Concurrent Users**: 120 per organization IP

## 🤝 Support

For issues or questions:
1. Check logs: `docker compose logs`
2. Review health status: `curl https://your-host/health/detailed`
3. Check Grafana dashboards
4. Review Prometheus metrics

## 📝 License

See individual component licenses:
- vLLM: Apache 2.0
- FastAPI: MIT
- Prometheus: Apache 2.0
- Grafana: AGPL 3.0
- Nginx: 2-clause BSD

---

**Built for enterprise-grade LLM inference with production-ready observability, resilience, and resource management.**
