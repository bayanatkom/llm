"""Main FastAPI application for the enterprise inference gateway."""
import os
import time
import asyncio
import itertools
from collections import defaultdict, deque
from typing import Optional, Dict, Deque, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.middleware.metrics import metrics_middleware, metrics_endpoint
from app.middleware.logging_middleware import logging_middleware, get_request_logger
from app.middleware.circuit_breaker import circuit_breaker_manager, CircuitBreakerOpenError
from app.services.health_check import health_check_service
from app.services.quota_manager import quota_manager
from app.services.cache_service import cache_service
from app.utils.token_counter import count_chat_tokens, token_counter
from app.middleware.metrics import (
    rate_limit_rejections, queue_depth, queue_wait_time,
    backend_requests, backend_duration, tokens_processed
)


# Validate configuration on startup
settings.validate()

# Round-robin iterator for chat backends
_rr_chat_index = itertools.cycle(range(len(settings.chat_backends)))

# HTTP client with optimized settings
limits = httpx.Limits(max_connections=3000, max_keepalive_connections=800, keepalive_expiry=30.0)
client = httpx.AsyncClient(timeout=httpx.Timeout(timeout=None, connect=5.0), limits=limits)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown."""
    # Startup
    await health_check_service.start()
    yield
    # Shutdown
    await health_check_service.stop()
    await client.aclose()


# Create FastAPI app
app = FastAPI(
    title="Enterprise Inference Gateway",
    version="1.0.0",
    description="Production-grade LLM inference gateway with observability and resilience",
    lifespan=lifespan
)

# Add middleware
app.middleware("http")(metrics_middleware)
app.middleware("http")(logging_middleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ----------------------------
# Helper Functions
# ----------------------------

def get_client_ip(req: Request) -> str:
    """Extract client IP from request."""
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if req.client:
        return req.client.host
    return "unknown"


def require_api_key(authorization: Optional[str]) -> None:
    """Validate API key."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.gateway_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


def backend_headers() -> dict:
    """Get headers for backend requests."""
    return {"Authorization": f"Bearer {settings.backend_api_key}"}


# ----------------------------
# Rate Limiting
# ----------------------------

_ip_hits: Dict[str, Deque[float]] = defaultdict(deque)


def enforce_rps(ip: str) -> None:
    """Enforce rate limiting per IP."""
    now = time.time()
    q = _ip_hits[ip]
    
    # Evict old hits
    while q and (now - q[0]) > settings.rps_window_secs:
        q.popleft()
    
    # Check limit
    allowed = max(settings.rps_burst, int(settings.max_rps_per_ip * settings.rps_window_secs))
    if len(q) >= allowed:
        rate_limit_rejections.labels(org_ip=ip, reason="rps_exceeded").inc()
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "1", "X-RateLimit-Limit": str(settings.max_rps_per_ip)}
        )
    q.append(now)


# ----------------------------
# Concurrency Control
# ----------------------------

_ip_sems: Dict[str, asyncio.Semaphore] = {}
_ip_last_seen: Dict[str, float] = {}
_gc_every = 1000
_req_counter = 0


def get_ip_sem(ip: str) -> asyncio.Semaphore:
    """Get or create semaphore for IP."""
    sem = _ip_sems.get(ip)
    if sem is None:
        sem = asyncio.Semaphore(settings.max_inflight_per_ip)
        _ip_sems[ip] = sem
    _ip_last_seen[ip] = time.time()
    return sem


def gc_idle(ip_idle_secs: float = 900.0) -> None:
    """Garbage collect idle IP data."""
    now = time.time()
    stale = [ip for ip, ts in _ip_last_seen.items() if (now - ts) > ip_idle_secs]
    for ip in stale:
        _ip_last_seen.pop(ip, None)
        _ip_sems.pop(ip, None)
        _ip_hits.pop(ip, None)


async def acquire_slot_or_429(sem: asyncio.Semaphore, ip: str) -> None:
    """Acquire concurrency slot or raise 429."""
    queue_start = time.time()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=settings.queue_timeout_secs)
        wait_time = time.time() - queue_start
        queue_wait_time.labels(org_ip=ip).observe(wait_time)
    except asyncio.TimeoutError:
        rate_limit_rejections.labels(org_ip=ip, reason="queue_timeout").inc()
        raise HTTPException(
            status_code=429,
            detail="Too many concurrent requests",
            headers={"Retry-After": str(int(max(1, settings.queue_timeout_secs)))}
        )


# ----------------------------
# Backend Proxy Functions
# ----------------------------

async def proxy_json(url: str, payload: dict, backend_type: str) -> JSONResponse:
    """Proxy JSON request to backend."""
    start_time = time.time()
    
    async def _do():
        r = await client.post(url, json=payload, headers=backend_headers())
        backend_requests.labels(backend=url, type=backend_type, status=r.status_code).inc()
        return JSONResponse(status_code=r.status_code, content=r.json())
    
    try:
        result = await circuit_breaker_manager.call(url, _do)
        duration = time.time() - start_time
        backend_duration.labels(backend=url, type=backend_type).observe(duration)
        return result
    except CircuitBreakerOpenError:
        raise HTTPException(status_code=503, detail="Backend temporarily unavailable")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Request timeout")


async def _stream_with_caps(r: httpx.Response) -> AsyncIterator[bytes]:
    """Stream response with timeout caps."""
    start = time.time()
    aiter = r.aiter_raw()
    
    while True:
        if time.time() - start > settings.max_request_secs:
            break
        
        try:
            chunk = await asyncio.wait_for(
                aiter.__anext__(),
                timeout=settings.stream_idle_timeout_secs
            )
        except asyncio.TimeoutError:
            break
        except StopAsyncIteration:
            break
        
        if chunk:
            yield chunk


async def proxy_stream(url: str, payload: dict, backend_type: str) -> StreamingResponse:
    """Proxy streaming request to backend."""
    start_time = time.time()
    
    async def gen():
        try:
            async def _stream():
                async with client.stream("POST", url, json=payload, headers=backend_headers()) as r:
                    backend_requests.labels(backend=url, type=backend_type, status=r.status_code).inc()
                    async for chunk in _stream_with_caps(r):
                        yield chunk
            
            async for chunk in circuit_breaker_manager.call(url, _stream):
                yield chunk
            
            duration = time.time() - start_time
            backend_duration.labels(backend=url, type=backend_type).observe(duration)
        
        except CircuitBreakerOpenError:
            yield b'data: {"error": "Backend temporarily unavailable"}\n\n'
    
    return StreamingResponse(gen(), media_type="text/event-stream")


async def admit(req: Request, authorization: Optional[str]) -> tuple[asyncio.Semaphore, str]:
    """Admission control: auth, rate limit, concurrency."""
    global _req_counter
    
    require_api_key(authorization)
    ip = get_client_ip(req)
    
    # Rate limiting
    enforce_rps(ip)
    
    # Concurrency control
    sem = get_ip_sem(ip)
    await acquire_slot_or_429(sem, ip)
    
    # Update queue depth metric
    queue_depth.labels(org_ip=ip).set(settings.max_inflight_per_ip - sem._value)
    
    # Periodic GC
    _req_counter += 1
    if _req_counter % _gc_every == 0:
        gc_idle()
    
    return sem, ip


# ----------------------------
# API Endpoints
# ----------------------------

@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "healthy", "backends": len(settings.chat_backends)}


@app.get("/health/detailed")
async def detailed_health():
    """Detailed health check with backend status."""
    return {
        "status": "healthy",
        "backends": health_check_service.get_all_status(),
        "cache": cache_service.get_stats()
    }


@app.get("/metrics")
async def metrics(request: Request):
    """Prometheus metrics endpoint."""
    return await metrics_endpoint(request)


@app.post("/v1/chat/completions")
async def chat_completions(req: Request, authorization: Optional[str] = Header(default=None)):
    """Chat completions endpoint (load-balanced across chat backends)."""
    sem, ip = await admit(req, authorization)
    log = get_request_logger(req)
    
    try:
        payload = await req.json()
        
        # Estimate tokens for quota check
        messages = payload.get("messages", [])
        estimated_tokens = count_chat_tokens(messages, "qwen")
        estimated_tokens += token_counter.estimate_completion_tokens(payload.get("max_tokens"))
        
        # Check quota
        allowed, reason = quota_manager.check_quota(ip, estimated_tokens)
        if not allowed:
            log.warning("quota_exceeded", reason=reason)
            raise HTTPException(status_code=429, detail=reason)
        
        # Check cache for non-streaming requests
        if not payload.get("stream"):
            cached = cache_service.get(
                model="qwen",
                messages=messages,
                temperature=payload.get("temperature", 0.7),
                max_tokens=payload.get("max_tokens", 2048)
            )
            if cached:
                log.info("cache_hit")
                return JSONResponse(content=cached)
        
        # Get healthy backend
        try:
            backend = health_check_service.get_healthy_backend("chat")
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        url = f"{backend}/v1/chat/completions"
        
        # Proxy request
        if payload.get("stream"):
            result = await proxy_stream(url, payload, "chat")
        else:
            result = await proxy_json(url, payload, "chat")
            # Cache successful responses
            if result.status_code == 200:
                cache_service.set(
                    response=result.body.decode() if hasattr(result, 'body') else result,
                    model="qwen",
                    messages=messages,
                    temperature=payload.get("temperature", 0.7),
                    max_tokens=payload.get("max_tokens", 2048)
                )
        
        # Record usage
        quota_manager.record_usage(ip, estimated_tokens)
        tokens_processed.labels(org_ip=ip, model="qwen", type="total").inc(estimated_tokens)
        
        return result
    
    finally:
        sem.release()
        queue_depth.labels(org_ip=ip).set(settings.max_inflight_per_ip - sem._value)


@app.post("/v1/text2sql")
async def text2sql(req: Request, authorization: Optional[str] = Header(default=None)):
    """Text2SQL endpoint."""
    sem, ip = await admit(req, authorization)
    log = get_request_logger(req)
    
    try:
        payload = await req.json()
        
        # Estimate tokens
        messages = payload.get("messages", [])
        estimated_tokens = count_chat_tokens(messages, "text2sql")
        estimated_tokens += token_counter.estimate_completion_tokens(payload.get("max_tokens"))
        
        # Check quota
        allowed, reason = quota_manager.check_quota(ip, estimated_tokens)
        if not allowed:
            log.warning("quota_exceeded", reason=reason)
            raise HTTPException(status_code=429, detail=reason)
        
        # Get backend
        try:
            backend = health_check_service.get_healthy_backend("text2sql")
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        url = f"{backend}/v1/chat/completions"
        
        # Proxy request
        if payload.get("stream"):
            result = await proxy_stream(url, payload, "text2sql")
        else:
            result = await proxy_json(url, payload, "text2sql")
        
        # Record usage
        quota_manager.record_usage(ip, estimated_tokens)
        tokens_processed.labels(org_ip=ip, model="text2sql", type="total").inc(estimated_tokens)
        
        return result
    
    finally:
        sem.release()
        queue_depth.labels(org_ip=ip).set(settings.max_inflight_per_ip - sem._value)


@app.post("/v1/embeddings")
async def embeddings(req: Request, authorization: Optional[str] = Header(default=None)):
    """Embeddings endpoint."""
    sem, ip = await admit(req, authorization)
    
    try:
        payload = await req.json()
        
        # Get backend
        try:
            backend = health_check_service.get_healthy_backend("embed")
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        url = f"{backend}/v1/embeddings"
        result = await proxy_json(url, payload, "embed")
        
        # Record usage (embeddings don't count toward token quota)
        quota_manager.record_usage(ip, 0)
        
        return result
    
    finally:
        sem.release()
        queue_depth.labels(org_ip=ip).set(settings.max_inflight_per_ip - sem._value)


@app.post("/v1/rerank")
async def rerank(req: Request, authorization: Optional[str] = Header(default=None)):
    """Rerank endpoint."""
    sem, ip = await admit(req, authorization)
    
    try:
        payload = await req.json()
        
        # Get backend
        try:
            backend = health_check_service.get_healthy_backend("rerank")
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        url = f"{backend}/rerank"
        result = await proxy_json(url, payload, "rerank")
        
        # Record usage
        quota_manager.record_usage(ip, 0)
        
        return result
    
    finally:
        sem.release()
        queue_depth.labels(org_ip=ip).set(settings.max_inflight_per_ip - sem._value)


@app.get("/admin/quota/{org_ip}")
async def get_quota(org_ip: str, authorization: Optional[str] = Header(default=None)):
    """Get quota usage for an organization."""
    require_api_key(authorization)
    return quota_manager.get_usage(org_ip)


@app.get("/admin/quotas")
async def get_all_quotas(authorization: Optional[str] = Header(default=None)):
    """Get quota usage for all organizations."""
    require_api_key(authorization)
    return quota_manager.get_all_usage()
