# Enterprise LLM Inference Platform

Production-ready, enterprise-grade LLM inference platform with comprehensive observability, resilience, and resource management features.

## 📋 Overview

This repository contains a complete enterprise implementation for running multiple LLM models on 4×L4 GPUs (24GB each) with:

- **Multi-model support**: Chat (Qwen2.5-7B), Text2SQL, Embeddings, Reranking
- **Enterprise features**: Observability, resilience, quotas, security
- **Production-ready**: Docker-based deployment with monitoring stack
- **SSL/TLS**: HTTPS support with existing certificates

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- NVIDIA GPU drivers + NVIDIA Container Toolkit
- 4× L4 GPUs (24GB each)
- SSL certificates (already configured in `../ssl_certificate/`)

### Deployment

```bash
# Navigate to the platform directory
cd inference-platform

# Create environment configuration
cp .env.example .env

# Edit configuration (set API keys)
nano .env

# Create cache directory
mkdir -p hf-cache

# Start the platform
docker compose up -d --build

# Start monitoring stack (optional but recommended)
docker compose -f docker-compose.monitoring.yml up -d

# Verify deployment
docker compose ps
```

## 📁 Project Structure

```
.
├── inference-platform/          # Enterprise inference platform
│   ├── gateway/                 # FastAPI gateway with enterprise features
│   │   ├── app/                 # Application code
│   │   │   ├── main.py          # Main FastAPI application
│   │   │   ├── config.py        # Configuration management
│   │   │   ├── middleware/      # Metrics, logging, circuit breakers
│   │   │   ├── services/        # Health checks, quotas, caching
│   │   │   └── utils/           # PII redaction, token counting
│   │   ├── Dockerfile           # Gateway container
│   │   └── requirements.txt     # Python dependencies
│   ├── nginx/                   # Reverse proxy with TLS
│   │   └── nginx.conf           # Nginx configuration
│   ├── monitoring/              # Monitoring stack
│   │   └── prometheus.yml       # Prometheus configuration
│   ├── docker-compose.yml       # Main services
│   ├── docker-compose.monitoring.yml  # Monitoring services
│   ├── .env.example             # Environment template
│   └── README.md                # Platform documentation
├── ssl_certificate/             # SSL certificates (pre-configured)
│   ├── cert-fullchain.crt       # Certificate chain
│   └── cert.key                 # Private key
├── Plan.md                      # Original implementation plan
├── Plan-Enterprise.md           # Enterprise features documentation
└── README.md                    # This file
```

## 🎯 Key Features

### Enterprise Capabilities

✅ **Observability**
- Prometheus metrics (20+ custom metrics)
- Structured JSON logging with correlation IDs
- PII redaction in logs
- Request/response audit trail

✅ **Resilience**
- Circuit breakers (5 failures → 30s recovery)
- Retry logic with exponential backoff
- Active health checks (every 10 seconds)
- Graceful shutdown with connection draining

✅ **Resource Management**
- Per-org rate limiting (50 RPS, burst 100)
- Per-org concurrency control (120 max)
- Per-org quotas (10M tokens/day, 100k requests/day)
- Token counting and tracking

✅ **Performance**
- Response caching (60s TTL, 10k entries)
- Gzip compression
- Optimized connection pooling
- Load balancing across backends

✅ **Security**
- TLS 1.2/1.3 with existing certificates
- Security headers (HSTS, CSP, X-Frame-Options)
- API key authentication
- Request validation

## 🔧 Configuration

### SSL Certificates

The platform is pre-configured to use certificates from `../ssl_certificate/`:
- `cert-fullchain.crt` - Full certificate chain
- `cert.key` - Private key

No additional certificate setup required!

### Environment Variables

Key configuration options in `.env`:

```bash
# API Keys
GATEWAY_API_KEY=your_strong_key_here
BACKEND_API_KEY=internal_key_here

# Rate Limiting
MAX_RPS_PER_IP=50
MAX_INFLIGHT_PER_IP=120

# Quotas
ORG_DAILY_TOKEN_LIMIT=10000000
ORG_DAILY_REQUEST_LIMIT=100000

# Timeouts
MAX_REQUEST_SECS=5400          # 90 min
STREAM_IDLE_TIMEOUT_SECS=180   # 3 min
```

See `.env.example` for all options.

## 📊 Monitoring

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

## 🔑 API Endpoints

### Chat Completions

```bash
curl -X POST https://your-host/v1/chat/completions \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7,
    "max_tokens": 2048
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

## 📚 Documentation

- **[inference-platform/README.md](inference-platform/README.md)** - Detailed platform documentation
- **[Plan-Enterprise.md](Plan-Enterprise.md)** - Enterprise features and architecture
- **[Plan.md](Plan.md)** - Original implementation plan

## 🛠️ Operations

### View Logs

```bash
cd inference-platform
docker logs -f inference-gateway
docker compose logs -f
```

### Check Health

```bash
curl https://your-host/health/detailed \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"
```

### Restart Services

```bash
cd inference-platform
docker compose restart gateway
docker compose restart
```

## 🔐 Security

1. **Change default API keys** in `.env`
2. **SSL certificates** pre-configured from `../ssl_certificate/`
3. **Restrict network access** to gateway only
4. **Enable PII redaction** in logs (enabled by default)
5. **Monitor quota usage** for anomalies
6. **Review audit logs** regularly

## 📈 Performance

Expected performance on 4×L4 GPUs:

- **Chat**: ~50-100 tokens/sec per GPU
- **Throughput**: ~100-200 requests/sec (with load balancing)
- **Latency**: p50 < 500ms, p95 < 2s (excluding generation time)
- **Concurrent Users**: 120 per organization IP

## 🤝 Support

For issues or questions:
1. Check logs: `docker compose logs`
2. Review health: `curl https://your-host/health/detailed`
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

**Enterprise-grade LLM inference platform with production-ready observability, resilience, and resource management.**
