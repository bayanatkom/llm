# Enterprise LLM Platform - Deployment Guide

## 🚀 Quick Deployment

### Prerequisites
- Docker & Docker Compose
- NVIDIA GPU drivers + Container Toolkit
- 4× L4 GPUs (24GB each)
- SSL certificates in `../ssl_certificate/`

### Deployment Steps

```bash
# 1. Navigate to platform directory
cd inference-platform

# 2. Configure environment
cp .env.example .env
nano .env  # Set required variables (see below)

# 3. Create cache directory
mkdir -p hf-cache

# 4. Deploy main platform
docker compose up -d --build

# 5. Deploy monitoring stack
docker compose -f docker-compose.monitoring.yml up -d

# 6. Verify deployment
docker compose ps
```

## 🔑 Required Environment Variables

Edit `.env` and set these **mandatory** variables:

```bash
# API Keys (REQUIRED - change these!)
GATEWAY_API_KEY=your-secure-gateway-key-here
BACKEND_API_KEY=your-secure-backend-key-here
HUGGING_FACE_HUB_TOKEN=your-hf-token-here

# Backend URLs (default values work out of the box)
CHAT_BACKENDS=http://chat0:8000,http://chat1:8000
TEXT2SQL_BACKEND=http://text2sql:8000
EMBED_BACKEND=http://embed:8000
RERANK_BACKEND=http://rerank:8000
```

**Optional**: Adjust rate limits, quotas, and timeouts as needed (defaults are production-ready).

## 🌐 Access URLs

Replace `your-host` with your server's domain/IP:

### Main Services (HTTPS)
- **API Gateway**: `https://your-host/`
- **API Documentation**: `https://your-host/docs`
- **Health Check**: `https://your-host/health`
- **Metrics**: `https://your-host/metrics`

### Monitoring (HTTPS)
- **Prometheus**: `https://your-host/prometheus/`
- **Grafana**: `https://your-host/grafana/` (admin/admin)

### API Endpoints
```bash
# Chat completions
POST https://your-host/v1/chat/completions

# Text2SQL
POST https://your-host/v1/text2sql

# Embeddings
POST https://your-host/v1/embeddings

# Rerank
POST https://your-host/v1/rerank
```

## 📋 Post-Deployment

### 1. Test API Access
```bash
curl https://your-host/health \
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"
```

### 2. Access Grafana
- URL: `https://your-host/grafana/`
- Login: admin/admin
- **Change password immediately**

### 3. Monitor Logs
```bash
docker logs -f inference-gateway
docker compose logs -f
```

## 🔒 SSL Configuration

SSL certificates are automatically loaded from `../ssl_certificate/`:
- `cert-fullchain.crt` (certificate chain)
- `cert.key` (private key)

All services (gateway, Prometheus, Grafana) use HTTPS via nginx.

## 📊 GPU Allocation

- **GPU 0**: Qwen2.5-7B (chat0)
- **GPU 1**: Qwen2.5-7B (chat1)
- **GPU 2**: Arctic-Text2SQL
- **GPU 3**: Snowflake-embed + BGE-reranker

## 🔧 Management Commands

```bash
# Restart services
docker compose restart

# View logs
docker compose logs -f gateway

# Stop platform
docker compose down

# Update and restart
docker compose up -d --build
```

## ✅ Deployment Checklist

- [ ] Set `GATEWAY_API_KEY` in `.env`
- [ ] Set `BACKEND_API_KEY` in `.env`
- [ ] Set `HUGGING_FACE_HUB_TOKEN` in `.env`
- [ ] SSL certificates present in `../ssl_certificate/`
- [ ] All containers running (`docker compose ps`)
- [ ] Health check passes
- [ ] Grafana accessible and password changed
- [ ] API endpoints responding

---

**Platform is ready for production use!**
