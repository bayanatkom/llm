# Enterprise-Grade LLM Inference Platform

## Architecture Overview

Multi-model inference platform running on 4×L4 GPUs (24GB each) with enterprise-grade observability, resilience, and resource management.

### GPU Allocation
- **GPU0**: Qwen2.5-7B-Instruct (chat0) - Load-balanced chat endpoint
- **GPU1**: Qwen2.5-7B-Instruct (chat1) - Load-balanced chat endpoint  
- **GPU2**: Arctic-Text2SQL-7B - Dedicated Text2SQL endpoint
- **GPU3**: Snowflake-arctic-embed-l-v2.0 + bge-reranker-v2-m3 (shared)

### Key Enterprise Features
1. **Observability**: Prometheus metrics, structured logging, distributed tracing
2. **Resilience**: Circuit breakers, retry logic, graceful shutdown, health checks
3. **Resource Management**: Per-org quotas, token counting, priority queuing
4. **Data Governance**: Audit logging, PII redaction, log retention
5. **Performance**: Response caching, compression, optimized connection pooling
6. **Security**: Enhanced headers, request validation, rate limit headers
7. **Monitoring**: Prometheus + Grafana + GPU metrics
8. **Operations**: Backup/restore, runbooks, load testing

## Deployment Structure

```
inference-platform/
├── gateway/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── metrics.py
│   │   │   ├── logging_middleware.py
│   │   │   └── circuit_breaker.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── health_check.py
│   │   │   ├── quota_manager.py
│   │   │   └── cache_service.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── pii_redaction.py
│   │       └── token_counter.py
│   ├── tests/
│   │   ├── test_integration.py
│   │   └── test_quotas.py
│   ├── Dockerfile
│   └── requirements.txt
├── monitoring/
│   ├── prometheus.yml
│   ├── grafana/
│   │   └── dashboards/
│   │       └── inference-dashboard.json
│   └── alertmanager.yml
├── nginx/
│   └── nginx.conf
├── scripts/
│   ├── backup.sh
│   ├── restore.sh
│   ├── health-check.sh
│   └── load-test.sh
├── docs/
│   ├── runbooks/
│   │   ├── high-cpu.md
│   │   ├── backend-failure.md
│   │   └── quota-exceeded.md
│   └── architecture.md
├── locust/
│   └── locustfile.py
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── .env.example
└── README.md
```

## Quick Start

### 1. Initial Setup
```bash
cd inference-platform
cp .env.example .env
# Edit .env with your API keys
mkdir -p certs hf-cache
# Copy your SSL certificates to certs/
```

### 2. Deploy Infrastructure
```bash
# Start inference services
docker compose up -d --build

# Start monitoring stack
docker compose -f docker-compose.monitoring.yml up -d

# Verify all services
docker compose ps
./scripts/health-check.sh
```

### 3. Access Services
- **API Gateway**: https://your-host/
- **Prometheus**: http://your-host:9090
- **Grafana**: http://your-host:3000 (admin/admin)
- **API Docs**: https://your-host/docs

## API Endpoints

### Chat Completions (Load-balanced across 2 Qwen replicas)
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

### Text2SQL (Dedicated endpoint)
```bash
curl -X POST https://your-host/v1/text2sql \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text2sql",
    "messages": [{"role": "user", "content": "Show me all users"}],
    "stream": false
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

## Monitoring & Observability

### Key Metrics
- **Request Metrics**: Total requests, latency (p50/p95/p99), error rates
- **Queue Metrics**: Queue depth, wait time, rejection rate
- **Backend Health**: Availability, response time per backend
- **GPU Metrics**: Memory usage, utilization per GPU
- **Quota Metrics**: Token usage, request counts per org
- **Rate Limit Metrics**: Rejections, burst usage

### Grafana Dashboards
1. **Overview Dashboard**: System health, request rates, error rates
2. **GPU Dashboard**: Memory usage, utilization, temperature
3. **Per-Org Dashboard**: Usage, quotas, rate limits
4. **Backend Dashboard**: Health, latency, error rates

### Alerts
- Backend unhealthy for >2 minutes
- GPU memory >90% for >5 minutes
- Error rate >5% for >2 minutes
- Queue depth >100 for >1 minute
- Rate limit rejections >100/min

## Resource Management

### Per-Organization Quotas
```python
# Configurable in .env
ORG_DAILY_TOKEN_LIMIT=10000000    # 10M tokens/day
ORG_DAILY_REQUEST_LIMIT=100000    # 100k requests/day
ORG_MONTHLY_TOKEN_LIMIT=300000000 # 300M tokens/month
```

### Rate Limiting
```python
# Per-IP rate limits
MAX_RPS_PER_IP=50          # 50 requests/sec average
RPS_BURST=100              # Allow bursts up to 100
MAX_INFLIGHT_PER_IP=120    # Max concurrent requests
QUEUE_TIMEOUT_SECS=2       # Queue admission timeout
```

### Long-Running Request Protection
```python
MAX_REQUEST_SECS=5400          # 90 min hard cap
STREAM_IDLE_TIMEOUT_SECS=180   # 3 min idle timeout
```

## Resilience Features

### Circuit Breakers
- Opens after 5 consecutive failures
- Recovery timeout: 30 seconds
- Prevents cascade failures

### Retry Logic
- Max 3 attempts with exponential backoff
- Retries on: 502, 503, 504 errors
- Backoff: 1s, 2s, 4s (with jitter)

### Health Checks
- Active backend monitoring every 10 seconds
- Automatic removal of unhealthy backends
- Graceful re-addition when healthy

### Graceful Shutdown
- Drains connections before shutdown
- Waits up to 30s for in-flight requests
- Rejects new requests during shutdown

## Security

### TLS/HTTPS
- TLS 1.2 and 1.3 only
- Strong cipher suites
- HSTS enabled

### Security Headers
- Strict-Transport-Security
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- X-XSS-Protection
- Referrer-Policy

### Request Validation
- JSON schema validation
- Max token limits enforced
- Input sanitization

### Rate Limit Headers
```
X-RateLimit-Limit: 50
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1706014800
```

## Data Governance

### Audit Logging
- All requests logged with correlation ID
- Includes: timestamp, org IP, endpoint, tokens, latency, status
- Structured JSON format
- PII automatically redacted

### Log Retention
- Hot logs: 7 days (fast access)
- Warm logs: 30 days (archived)
- Automatic rotation and cleanup

### PII Redaction
- Email addresses → [EMAIL]
- Phone numbers → [PHONE]
- SSNs → [SSN]
- Credit cards → [CC]

## Operations

### Backup
```bash
./scripts/backup.sh
# Backs up: .env, certs/, nginx.conf, docker-compose.yml
# Stores in: ./backups/YYYY-MM-DD-HH-MM-SS/
```

### Restore
```bash
./scripts/restore.sh ./backups/2026-01-23-10-00-00/
```

### Health Check
```bash
./scripts/health-check.sh
# Checks: Gateway, all backends, monitoring stack
```

### Load Testing
```bash
./scripts/load-test.sh
# Runs Locust load test
# Simulates 100 concurrent users
```

## Troubleshooting

### High CPU Usage
See: `docs/runbooks/high-cpu.md`

### Backend Failure
See: `docs/runbooks/backend-failure.md`

### Quota Exceeded
See: `docs/runbooks/quota-exceeded.md`

### GPU Out of Memory
See: `docs/runbooks/gpu-oom.md`

## Performance Tuning

### Response Caching
- Caches identical requests for 60 seconds
- Cache key: hash(model + messages + params)
- Max 10,000 cached responses

### Connection Pooling
- Max connections: 3000
- Keepalive connections: 800
- Keepalive expiry: 30s

### Compression
- Gzip enabled for responses >1KB
- Reduces bandwidth by ~70%

## Scaling Recommendations

### Vertical Scaling (Per GPU)
- Adjust `--gpu-memory-utilization` (0.85-0.95)
- Tune `--max-model-len` based on workload
- Enable `--enable-prefix-caching` for repeated prompts

### Horizontal Scaling (Add GPUs)
- Add more chat replicas for higher throughput
- Separate embedding/rerank to dedicated GPUs
- Use multiple gateway replicas

### Gateway Scaling
```yaml
gateway:
  deploy:
    replicas: 3  # Run 3 gateway instances
```

## Cost Optimization

### Token Usage Tracking
- Per-org token counting
- Daily/monthly reports
- Cost allocation by organization

### Efficient Model Loading
- Shared HF cache across containers
- Persistent model storage
- Lazy loading where possible

## Support & Maintenance

### Regular Tasks
- Daily: Review metrics, check alerts
- Weekly: Analyze quota usage, review logs
- Monthly: Update models, security patches

### Monitoring Checklist
- [ ] All backends healthy
- [ ] GPU memory <85%
- [ ] Error rate <1%
- [ ] Queue depth <50
- [ ] No critical alerts

## License & Credits

Built with:
- vLLM (Apache 2.0)
- FastAPI (MIT)
- Prometheus (Apache 2.0)
- Grafana (AGPL 3.0)
- Nginx (2-clause BSD)
