IP == organization (behind Nginx)

You want ~50 requests/sec per org IP (rate limit)

You want high concurrency per org because one chat triggers multiple small LLM calls (concurrency cap + queueing)

You want queue timeout only (admission timeout), NOT “generation timeout”

You still want long-running deep agent calls (max lifetime + streaming idle timeout, very generous)

Separate endpoint for Text2SQL

HTTPS with your uploaded certs

Docker, 4× L4, Qwen load-balanced across 2 replicas

Folder layout
inference-box/
  docker-compose.yml
  .env
  certs/
    fullchain.pem
    privkey.pem
  nginx/
    nginx.conf
  gateway/
    Dockerfile
    requirements.txt
    app.py

1) .env (COPY/PASTE)
# Public key clients send to your gateway
GATEWAY_API_KEY=CHANGE_ME_STRONG

# Internal key gateway uses to call vLLM backends
BACKEND_API_KEY=INTERNAL_ONLY_CHANGE_ME

# Optional HF token if any model is gated
HUGGING_FACE_HUB_TOKEN=

# HF cache path on host (persists downloads)
HF_HOME=./hf-cache

# === Org/IP traffic controls ===

# Allow ~50 requests/sec per org IP
MAX_RPS_PER_IP=50
RPS_WINDOW_SECS=1
RPS_BURST=100

# Allow high concurrency per org IP (because one chat fans out into many calls)
MAX_INFLIGHT_PER_IP=120

# Queueing timeout (admission only). If no slot within this -> 429
QUEUE_TIMEOUT_SECS=2

# Long-run safety caps (NOT a “generation timeout”):
# Hard cap total request lifetime (protects against infinite sockets)
MAX_REQUEST_SECS=5400          # 90 minutes
# If streaming produces no bytes for this long -> cut the stream
STREAM_IDLE_TIMEOUT_SECS=180   # 3 minutes

# Gateway workers
GATEWAY_WORKERS=4

2) docker-compose.yml (COPY/PASTE)
version: "3.9"

services:
  # --------------------
  # Qwen Chat replicas (GPU0, GPU1)
  # --------------------
  chat0:
    image: vllm/vllm-openai:latest
    container_name: vllm-chat0
    restart: unless-stopped
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - NVIDIA_VISIBLE_DEVICES=0
    volumes:
      - ${HF_HOME:-./hf-cache}:/root/.cache/huggingface
    expose:
      - "8000"
    command: >
      vllm serve Qwen/Qwen2.5-7B-Instruct
      --host 0.0.0.0 --port 8000
      --api-key ${BACKEND_API_KEY}
      --max-model-len 8192
      --gpu-memory-utilization 0.90
    device_requests:
      - driver: nvidia
        count: 1
        capabilities: [gpu]

  chat1:
    image: vllm/vllm-openai:latest
    container_name: vllm-chat1
    restart: unless-stopped
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - NVIDIA_VISIBLE_DEVICES=1
    volumes:
      - ${HF_HOME:-./hf-cache}:/root/.cache/huggingface
    expose:
      - "8000"
    command: >
      vllm serve Qwen/Qwen2.5-7B-Instruct
      --host 0.0.0.0 --port 8000
      --api-key ${BACKEND_API_KEY}
      --max-model-len 8192
      --gpu-memory-utilization 0.90
    device_requests:
      - driver: nvidia
        count: 1
        capabilities: [gpu]

  # --------------------
  # Text2SQL (GPU2)
  # --------------------
  text2sql:
    image: vllm/vllm-openai:latest
    container_name: vllm-text2sql
    restart: unless-stopped
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - NVIDIA_VISIBLE_DEVICES=2
    volumes:
      - ${HF_HOME:-./hf-cache}:/root/.cache/huggingface
    expose:
      - "8000"
    command: >
      vllm serve Snowflake/Arctic-Text2SQL-R1-7B
      --host 0.0.0.0 --port 8000
      --api-key ${BACKEND_API_KEY}
      --max-model-len 8192
      --gpu-memory-utilization 0.90
    device_requests:
      - driver: nvidia
        count: 1
        capabilities: [gpu]

  # --------------------
  # Embeddings (GPU3)
  # --------------------
  embed:
    image: vllm/vllm-openai:latest
    container_name: vllm-embed
    restart: unless-stopped
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - NVIDIA_VISIBLE_DEVICES=3
    volumes:
      - ${HF_HOME:-./hf-cache}:/root/.cache/huggingface
    expose:
      - "8000"
    command: >
      vllm serve Snowflake/snowflake-arctic-embed-l-v2.0
      --runner pooling
      --host 0.0.0.0 --port 8000
      --api-key ${BACKEND_API_KEY}
      --gpu-memory-utilization 0.80
    device_requests:
      - driver: nvidia
        count: 1
        capabilities: [gpu]

  # --------------------
  # Reranker (GPU3)
  # --------------------
  rerank:
    image: vllm/vllm-openai:latest
    container_name: vllm-rerank
    restart: unless-stopped
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - NVIDIA_VISIBLE_DEVICES=3
    volumes:
      - ${HF_HOME:-./hf-cache}:/root/.cache/huggingface
    expose:
      - "8000"
    command: >
      vllm serve BAAI/bge-reranker-v2-m3
      --runner pooling
      --host 0.0.0.0 --port 8000
      --api-key ${BACKEND_API_KEY}
      --gpu-memory-utilization 0.80
    device_requests:
      - driver: nvidia
        count: 1
        capabilities: [gpu]

  # --------------------
  # Gateway (CPU) - multiple workers
  # --------------------
  gateway:
    build: ./gateway
    container_name: inference-gateway
    restart: unless-stopped
    depends_on:
      - chat0
      - chat1
      - text2sql
      - embed
      - rerank
    environment:
      - GATEWAY_API_KEY=${GATEWAY_API_KEY}
      - BACKEND_API_KEY=${BACKEND_API_KEY}
      - CHAT_BACKENDS=http://chat0:8000,http://chat1:8000
      - TEXT2SQL_BACKEND=http://text2sql:8000
      - EMBED_BACKEND=http://embed:8000
      - RERANK_BACKEND=http://rerank:8000
      - MAX_RPS_PER_IP=${MAX_RPS_PER_IP}
      - RPS_WINDOW_SECS=${RPS_WINDOW_SECS}
      - RPS_BURST=${RPS_BURST}
      - MAX_INFLIGHT_PER_IP=${MAX_INFLIGHT_PER_IP}
      - QUEUE_TIMEOUT_SECS=${QUEUE_TIMEOUT_SECS}
      - MAX_REQUEST_SECS=${MAX_REQUEST_SECS}
      - STREAM_IDLE_TIMEOUT_SECS=${STREAM_IDLE_TIMEOUT_SECS}
      - GATEWAY_WORKERS=${GATEWAY_WORKERS}
    expose:
      - "9000"

  # --------------------
  # Nginx TLS (public)
  # --------------------
  nginx:
    image: nginx:1.27-alpine
    container_name: inference-nginx
    restart: unless-stopped
    depends_on:
      - gateway
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs/fullchain.pem:/etc/nginx/certs/fullchain.pem:ro
      - ./certs/privkey.pem:/etc/nginx/certs/privkey.pem:ro

3) nginx/nginx.conf (COPY/PASTE)

HTTPS + streaming safe + very long read timeout (because you want long agent runs).

worker_processes auto;

events { worker_connections 4096; }

http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;

  sendfile on;
  tcp_nopush on;
  tcp_nodelay on;
  keepalive_timeout 65;

  client_max_body_size 50m;

  server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
  }

  server {
    listen 443 ssl http2;
    server_name _;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Streaming stability
    proxy_buffering off;
    proxy_cache off;
    proxy_http_version 1.1;

    # Not a “generation timeout”. Just allow long sessions.
    proxy_connect_timeout 5s;
    proxy_send_timeout 6000s;
    proxy_read_timeout 6000s;

    location / {
      proxy_pass http://gateway:9000;

      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

      proxy_set_header Authorization $http_authorization;

      chunked_transfer_encoding on;
    }
  }
}

4) Gateway (COPY/PASTE)
gateway/requirements.txt
fastapi==0.115.8
uvicorn[standard]==0.34.0
httpx==0.27.2

gateway/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 9000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 9000 --workers ${GATEWAY_WORKERS:-4}"]

gateway/app.py

This implements:

API key auth

Rate limit per IP (50 RPS avg with burst)

Concurrency per IP (admission queue + timeout)

Max request lifetime (hard cap)

Streaming idle timeout (silence cap)

Load-balanced Qwen (/v1/chat/completions)

Separate Text2SQL endpoint (/v1/text2sql)

OpenAI embeddings path (/v1/embeddings)

Rerank wrapper (/v1/rerank → vLLM /rerank)

import os
import time
import asyncio
import itertools
from collections import defaultdict, deque
from typing import Optional, Dict, Deque, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Enterprise Inference Gateway", version="1.0")

# ----------------------------
# Env
# ----------------------------
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY", "")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")

CHAT_BACKENDS = [b.strip() for b in os.getenv("CHAT_BACKENDS", "").split(",") if b.strip()]
TEXT2SQL_BACKEND = os.getenv("TEXT2SQL_BACKEND", "").strip()
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "").strip()
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "").strip()

# Rate limiting per IP
MAX_RPS_PER_IP = float(os.getenv("MAX_RPS_PER_IP", "50"))
RPS_WINDOW_SECS = float(os.getenv("RPS_WINDOW_SECS", "1"))
RPS_BURST = int(os.getenv("RPS_BURST", "100"))

# Per-IP concurrency control
MAX_INFLIGHT_PER_IP = int(os.getenv("MAX_INFLIGHT_PER_IP", "120"))
QUEUE_TIMEOUT_SECS = float(os.getenv("QUEUE_TIMEOUT_SECS", "2"))

# Long-run caps (safety, not payload limits)
MAX_REQUEST_SECS = float(os.getenv("MAX_REQUEST_SECS", "5400"))
STREAM_IDLE_TIMEOUT_SECS = float(os.getenv("STREAM_IDLE_TIMEOUT_SECS", "180"))

if not (GATEWAY_API_KEY and BACKEND_API_KEY):
    raise RuntimeError("Missing GATEWAY_API_KEY or BACKEND_API_KEY")
if not (CHAT_BACKENDS and TEXT2SQL_BACKEND and EMBED_BACKEND and RERANK_BACKEND):
    raise RuntimeError("Missing one or more backend URLs")

_rr_chat = itertools.cycle(CHAT_BACKENDS)

# ----------------------------
# HTTP client (no short generation timeout)
# ----------------------------
limits = httpx.Limits(max_connections=3000, max_keepalive_connections=800)
client = httpx.AsyncClient(timeout=httpx.Timeout(timeout=None, connect=5.0), limits=limits)

def require_api_key(authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != GATEWAY_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

def backend_headers() -> dict:
    return {"Authorization": f"Bearer {BACKEND_API_KEY}"}

def get_client_ip(req: Request) -> str:
    # Trust nginx X-Forwarded-For (left-most is client)
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if req.client:
        return req.client.host
    return "unknown"

# ----------------------------
# Per-IP RPS limiter (sliding window w/ burst)
# ----------------------------
_ip_hits: Dict[str, Deque[float]] = defaultdict(deque)

def enforce_rps(ip: str) -> None:
    now = time.time()
    q = _ip_hits[ip]

    # evict old hits
    while q and (now - q[0]) > RPS_WINDOW_SECS:
        q.popleft()

    # Allowed hits in window
    allowed = max(RPS_BURST, int(MAX_RPS_PER_IP * RPS_WINDOW_SECS))
    if len(q) >= allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "1"})
    q.append(now)

# ----------------------------
# Per-IP concurrency (queue + admission timeout)
# ----------------------------
_ip_sems: Dict[str, asyncio.Semaphore] = {}
_ip_last_seen: Dict[str, float] = {}
_gc_every = 1000
_req_counter = 0

def get_ip_sem(ip: str) -> asyncio.Semaphore:
    sem = _ip_sems.get(ip)
    if sem is None:
        sem = asyncio.Semaphore(MAX_INFLIGHT_PER_IP)
        _ip_sems[ip] = sem
    _ip_last_seen[ip] = time.time()
    return sem

def gc_idle(ip_idle_secs: float = 900.0) -> None:
    now = time.time()
    stale = [ip for ip, ts in _ip_last_seen.items() if (now - ts) > ip_idle_secs]
    for ip in stale:
        _ip_last_seen.pop(ip, None)
        _ip_sems.pop(ip, None)
        _ip_hits.pop(ip, None)

async def acquire_slot_or_429(sem: asyncio.Semaphore) -> None:
    try:
        await asyncio.wait_for(sem.acquire(), timeout=QUEUE_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=429,
            detail="Too many concurrent requests from this org IP",
            headers={"Retry-After": str(int(max(1, QUEUE_TIMEOUT_SECS)))},
        )

# ----------------------------
# Proxy helpers
# ----------------------------
async def proxy_json(url: str, payload: dict) -> JSONResponse:
    async def _do():
        r = await client.post(url, json=payload, headers=backend_headers())
        return JSONResponse(status_code=r.status_code, content=r.json())

    try:
        return await asyncio.wait_for(_do(), timeout=MAX_REQUEST_SECS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Request exceeded max lifetime")

async def _stream_with_caps(r: httpx.Response) -> AsyncIterator[bytes]:
    start = time.time()
    aiter = r.aiter_raw()

    while True:
        # Hard lifetime cap
        if time.time() - start > MAX_REQUEST_SECS:
            break

        # Idle cap (no bytes for too long)
        try:
            chunk = await asyncio.wait_for(aiter.__anext__(), timeout=STREAM_IDLE_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            break
        except StopAsyncIteration:
            break

        if chunk:
            yield chunk

async def proxy_stream(url: str, payload: dict) -> StreamingResponse:
    async def gen():
        async with client.stream("POST", url, json=payload, headers=backend_headers()) as r:
            async for chunk in _stream_with_caps(r):
                yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")

async def admit(req: Request, authorization: Optional[str]) -> asyncio.Semaphore:
    global _req_counter
    require_api_key(authorization)

    ip = get_client_ip(req)

    # RPS limit first (cheap rejection)
    enforce_rps(ip)

    # Concurrency admission next
    sem = get_ip_sem(ip)
    await acquire_slot_or_429(sem)

    _req_counter += 1
    if _req_counter % _gc_every == 0:
        gc_idle()

    return sem

@app.get("/health")
async def health():
    return {"ok": True, "chat_backends": len(CHAT_BACKENDS)}

# ----------------------------
# Public endpoints
# ----------------------------
@app.post("/v1/chat/completions")
async def chat_completions(req: Request, authorization: Optional[str] = Header(default=None)):
    sem = await admit(req, authorization)
    try:
        payload = await req.json()
        backend = next(_rr_chat)
        url = f"{backend}/v1/chat/completions"
        if payload.get("stream") is True:
            return await proxy_stream(url, payload)
        return await proxy_json(url, payload)
    finally:
        sem.release()

@app.post("/v1/text2sql")
async def text2sql(req: Request, authorization: Optional[str] = Header(default=None)):
    sem = await admit(req, authorization)
    try:
        payload = await req.json()
        url = f"{TEXT2SQL_BACKEND}/v1/chat/completions"
        if payload.get("stream") is True:
            return await proxy_stream(url, payload)
        return await proxy_json(url, payload)
    finally:
        sem.release()

@app.post("/v1/embeddings")
async def embeddings(req: Request, authorization: Optional[str] = Header(default=None)):
    sem = await admit(req, authorization)
    try:
        payload = await req.json()
        url = f"{EMBED_BACKEND}/v1/embeddings"
        return await proxy_json(url, payload)
    finally:
        sem.release()

@app.post("/v1/rerank")
async def rerank(req: Request, authorization: Optional[str] = Header(default=None)):
    sem = await admit(req, authorization)
    try:
        payload = await req.json()
        url = f"{RERANK_BACKEND}/rerank"
        return await proxy_json(url, payload)
    finally:
        sem.release()

5) Run (COPY/PASTE)
cd inference-box
docker compose up -d --build
docker compose ps

6) Public endpoints

All HTTPS via Nginx:

https://<host>/v1/chat/completions ✅ OpenAI-compatible

https://<host>/v1/embeddings ✅ OpenAI-compatible

https://<host>/v1/text2sql (custom path, OpenAI chat payload)

https://<host>/v1/rerank (custom wrapper)

Auth for all:
Authorization: Bearer <GATEWAY_API_KEY>

The honest warning you shouldn’t ignore

If your “org IP” is actually a NAT with many users behind it, 50 RPS + 120 concurrent might still be too low or too high depending on their behavior. You’ll tune:

MAX_RPS_PER_IP, RPS_BURST

MAX_INFLIGHT_PER_IP

QUEUE_TIMEOUT_SECS

But this is the correct control plane: rate + concurrency + admission queue + long-run caps.