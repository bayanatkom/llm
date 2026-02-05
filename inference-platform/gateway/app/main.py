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
from contextlib import asynccontextmanager
import json

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
_rr_chat_index = itertools.cycle(range(len(settings.get_chat_backends())))

# Model name mapping (OpenRouter-style -> HuggingFace-style)
# Consolidated: Single Qwen 14B AWQ model for all tasks (chat + text2sql)
MODEL_ALIASES = {
    # Chat/General model - Qwen 14B AWQ (95K context with YaRN)
    "qwen/qwen-2.5-14b-instruct": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "qwen/qwen-2.5-14b-instruct-awq": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "qwen-2.5-14b-instruct": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "qwen-2.5-14b": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    # Legacy 7B aliases redirect to 14B AWQ
    "qwen/qwen-2.5-7b-instruct": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "qwen-2.5-7b-instruct": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    # Text2SQL aliases - now handled by Qwen 14B AWQ
    "snowflake/arctic-text2sql-r1-7b": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "arctic-text2sql-7b": "Qwen/Qwen2.5-14B-Instruct-AWQ",
    "arctic-text2sql-r1-7b": "Qwen/Qwen2.5-14B-Instruct-AWQ",
}


def resolve_model_name(model: str) -> str:
    """Resolve model alias to actual model name."""
    return MODEL_ALIASES.get(model.lower(), model)


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

# Add middleware (NO GZip - it breaks SSE streaming for litellm/openrouter)
app.middleware("http")(metrics_middleware)
app.middleware("http")(logging_middleware)
# Removed GZipMiddleware as it can corrupt SSE text/event-stream responses


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


@asynccontextmanager
async def proxy_acq(ip: str) -> AsyncIterator[None]:
    """Acquire semaphore for IP with queueing timeout."""
    sem = get_ip_sem(ip)
    
    # Periodic GC
    global _req_counter
    _req_counter += 1
    if _req_counter % _gc_every == 0:
        gc_idle()
    
    # Try to acquire within timeout
    start = time.time()
    acquired = False
    try:
        queue_depth.labels(org_ip=ip).inc()
        
        acquired = await asyncio.wait_for(
            sem.acquire(),
            timeout=settings.queue_timeout_secs
        )
        
        elapsed = time.time() - start
        queue_wait_time.labels(org_ip=ip).observe(elapsed)
        yield
        
    except asyncio.TimeoutError:
        rate_limit_rejections.labels(org_ip=ip, reason="queue_timeout").inc()
        raise HTTPException(
            status_code=429,
            detail="Queue is full; please retry",
            headers={"Retry-After": "5"}
        )
    finally:
        queue_depth.labels(org_ip=ip).dec()
        if acquired:
            sem.release()


# ----------------------------
# Proxy Functions
# ----------------------------

async def proxy_json(url: str, payload: dict, backend_type: str) -> dict:
    """Proxy JSON request to backend."""
    try:
        with circuit_breaker_manager.get_breaker(url):
            backend_requests.labels(backend=url, type=backend_type, status="started").inc()
            start = time.time()
            
            response = await client.post(
                url,
                json=payload,
                headers=backend_headers(),
                timeout=settings.max_request_secs
            )
            
            backend_duration.labels(backend=url, type=backend_type).observe(time.time() - start)
            response.raise_for_status()
            return response.json()
            
    except CircuitBreakerOpenError:
        raise HTTPException(status_code=503, detail="Backend temporarily unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Backend request timeout")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="Backend rate limit exceeded")
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backend error: {str(e)}")


def sse_error(message: str, err_type: str = "api_error", code: str = None) -> bytes:
    """Create OpenAI/OpenRouter-compatible SSE error chunk."""
    payload = {
        "error": {
            "message": message,
            "type": err_type,
            "code": code
        }
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def clean_stream_chunk(chunk_data: dict) -> dict:
    """Clean vLLM-specific fields from streaming chunks to improve compatibility."""
    # Remove vLLM-specific fields that can confuse other parsers
    vllm_fields_to_remove = [
        "prompt_token_ids", "prompt_logprobs", "token_ids",
        "reasoning_content", "stop_reason", "kv_transfer_params"
    ]
    
    # Clean top-level fields
    for field in vllm_fields_to_remove:
        chunk_data.pop(field, None)
    
    # Clean choice-level fields
    if "choices" in chunk_data:
        for choice in chunk_data["choices"]:
            for field in vllm_fields_to_remove:
                choice.pop(field, None)
            # Clean delta fields
            if "delta" in choice:
                for field in vllm_fields_to_remove:
                    choice["delta"].pop(field, None)
            # Clean message fields
            if "message" in choice:
                for field in vllm_fields_to_remove:
                    choice["message"].pop(field, None)
    
    return chunk_data


def normalize_error_chunk(chunk_data: dict) -> dict:
    """Normalize error chunks to OpenAI/OpenRouter format."""
    if "error" in chunk_data:
        # If error is a string, convert to proper object format
        if isinstance(chunk_data["error"], str):
            chunk_data = {
                "error": {
                    "message": chunk_data["error"],
                    "type": "api_error",
                    "code": None
                }
            }
    return chunk_data


async def stream_proxy(url: str, payload: dict, backend_type: str, request: Request = None) -> StreamingResponse:
    """Proxy streaming request to backend with response cleanup for compatibility."""
    payload["stream"] = True
    
    # Get request-specific logger if request is provided, otherwise use base logger
    if request:
        log = get_request_logger(request)
    else:
        import structlog
        log = structlog.get_logger()
    
    async def generate():
        """Stream generator with timeout handling and response cleanup."""
        try:
            with circuit_breaker_manager.get_breaker(url):
                backend_requests.labels(backend=url, type=backend_type, status="started").inc()
                start = time.time()
                
                # Reset idle timer
                last_chunk_time = time.time()
                
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=backend_headers(),
                    timeout=httpx.Timeout(
                        connect=5.0,
                        read=settings.stream_idle_timeout_secs,
                        write=None,
                        pool=None
                    )
                ) as response:
                    # Problem 1 fix: Don't raise_for_status() - handle non-2xx by reading body
                    if response.status_code >= 400:
                        raw = await response.aread()
                        msg = raw.decode("utf-8", errors="replace")
                        err_type = "api_error"
                        code = str(response.status_code)
                        # Try to extract message from JSON error response
                        try:
                            err_json = json.loads(msg)
                            if isinstance(err_json.get("error"), dict):
                                msg = err_json["error"].get("message", msg)
                                err_type = err_json["error"].get("type", err_type)
                                code = err_json["error"].get("code", code)
                            elif isinstance(err_json.get("error"), str):
                                msg = err_json["error"]
                            elif "message" in err_json:
                                msg = err_json["message"]
                        except json.JSONDecodeError:
                            pass  # Use raw message
                        log.error(f"Backend returned {response.status_code} for {backend_type}: {msg[:200]}")
                        yield sse_error(msg[:500], err_type, code)
                        yield b"data: [DONE]\n\n"
                        return
                    
                    backend_duration.labels(backend=url, type=backend_type).observe(time.time() - start)
                    
                    async for line in response.aiter_lines():
                        current_time = time.time()
                        if current_time - last_chunk_time > settings.stream_idle_timeout_secs:
                            log.warning(f"Stream idle timeout exceeded for {backend_type}")
                            break
                        last_chunk_time = current_time
                        
                        # Problem 2 fix: Only forward data: lines, skip other SSE line types
                        if line.startswith("data: "):
                            data_content = line[6:]  # Remove "data: " prefix
                            if data_content.strip() == "[DONE]":
                                yield b"data: [DONE]\n\n"
                            else:
                                try:
                                    chunk_json = json.loads(data_content)
                                    
                                    # Handle error chunks - normalize to OpenAI format
                                    if "error" in chunk_json:
                                        chunk_json = normalize_error_chunk(chunk_json)
                                        yield f"data: {json.dumps(chunk_json)}\n\n".encode()
                                        continue
                                    
                                    cleaned_chunk = clean_stream_chunk(chunk_json)
                                    yield f"data: {json.dumps(cleaned_chunk)}\n\n".encode()
                                except json.JSONDecodeError:
                                    # Pass through non-JSON data as-is
                                    yield f"{line}\n\n".encode()
                        # Non data: lines are silently skipped (event:, id:, retry:, comments, etc.)
                        
        except CircuitBreakerOpenError:
            yield sse_error("Backend temporarily unavailable", "service_unavailable", "backend_unavailable")
            yield b"data: [DONE]\n\n"
        except httpx.TimeoutException as e:
            msg = str(e) or "Stream timeout"
            log.error(f"Stream timeout for {backend_type}: {msg}")
            yield sse_error(msg[:500], "timeout", "stream_timeout")
            yield b"data: [DONE]\n\n"
        except Exception as e:
            # Problem 3 fix: Use real exception message instead of generic "Stream error"
            msg = str(e) or e.__class__.__name__
            log.error(f"Stream error for {backend_type}: {msg}")
            yield sse_error(msg[:500], "api_error", "stream_proxy_exception")
            yield b"data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


# ----------------------------
# Routes
# ----------------------------

@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "Enterprise Inference Gateway", "status": "healthy"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    backends_status = health_check_service.get_status()
    all_healthy = all(
        len(backends) > 0
        for backends in backends_status.values()
    )
    
    status_code = 200 if all_healthy else 503
    return JSONResponse(
        content={
            "status": "healthy" if all_healthy else "degraded",
            "backends": backends_status
        },
        status_code=status_code
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return await metrics_endpoint()


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI + OpenRouter compatible format)."""
    import time
    current_time = int(time.time())
    
    # Combined OpenAI + OpenRouter compatible schema
    models = [
        # Chat & Text2SQL model - Qwen 2.5 14B Instruct AWQ (95K context with YaRN)
        {
            # OpenAI standard fields
            "id": "qwen/qwen-2.5-14b-instruct",
            "object": "model",
            "created": current_time,
            "owned_by": "bayanatkom",
            "permission": [
                {
                    "id": "modelperm-qwen",
                    "object": "model_permission",
                    "created": current_time,
                    "allow_create_engine": False,
                    "allow_sampling": True,
                    "allow_logprobs": True,
                    "allow_search_indices": False,
                    "allow_view": True,
                    "allow_fine_tuning": False,
                    "organization": "*",
                    "group": None,
                    "is_blocking": False
                }
            ],
            "root": "qwen/qwen-2.5-14b-instruct",
            "parent": None,
            # OpenRouter additional fields
            "canonical_slug": "qwen/qwen-2.5-14b-instruct",
            "name": "Qwen 2.5 14B Instruct AWQ",
            "description": "Qwen 2.5 14B Instruct AWQ - 95K context with YaRN, 4-bit AWQ quantization, supports tool calling. Handles chat and text2SQL. Running on 4x L4 GPUs with ~3.9x concurrent capacity.",
            "context_length": 97280,
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "tokenizer": "Qwen",
                "instruct_type": "chat"
            },
            "pricing": {
                "prompt": "0",
                "completion": "0",
                "request": "0"
            },
            "top_provider": {
                "context_length": 97280,
                "max_completion_tokens": 8192,
                "is_moderated": False
            },
            "supported_parameters": [
                "temperature",
                "top_p",
                "max_tokens",
                "stream",
                "stop",
                "frequency_penalty",
                "presence_penalty",
                "tools",
                "tool_choice"
            ]
        },
        # Legacy Text2SQL alias (redirects to Qwen 14B)
        {
            # OpenAI standard fields
            "id": "snowflake/arctic-text2sql-r1-7b",
            "object": "model",
            "created": current_time,
            "owned_by": "bayanatkom",
            "permission": [
                {
                    "id": "modelperm-text2sql",
                    "object": "model_permission",
                    "created": current_time,
                    "allow_create_engine": False,
                    "allow_sampling": True,
                    "allow_logprobs": True,
                    "allow_search_indices": False,
                    "allow_view": True,
                    "allow_fine_tuning": False,
                    "organization": "*",
                    "group": None,
                    "is_blocking": False
                }
            ],
            "root": "snowflake/arctic-text2sql-r1-7b",
            "parent": None,
            # OpenRouter additional fields
            "canonical_slug": "snowflake/arctic-text2sql-r1-7b",
            "name": "Text2SQL (Legacy - uses Qwen 14B)",
            "description": "Legacy alias - redirects to Qwen 2.5 14B Instruct for SQL generation. Use qwen/qwen-2.5-14b-instruct for 128K context.",
            "context_length": 131072,
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "tokenizer": "Qwen",
                "instruct_type": "chat"
            },
            "pricing": {
                "prompt": "0",
                "completion": "0",
                "request": "0"
            },
            "top_provider": {
                "context_length": 131072,
                "max_completion_tokens": 8192,
                "is_moderated": False
            },
            "supported_parameters": [
                "temperature",
                "top_p",
                "max_tokens",
                "stream",
                "stop",
                "tools",
                "tool_choice"
            ]
        }
    ]
    
    return {
        "object": "list",
        "data": models
    }


@app.get("/api/v1/models")
async def list_models_openrouter():
    """List available models (OpenRouter API path alias).
    
    Many OpenRouter-compatible tools call /api/v1/models instead of /v1/models.
    This alias returns the same data in OpenRouter-preferred format.
    """
    response = await list_models()
    # OpenRouter style typically omits "object": "list"
    return {"data": response["data"]}


@app.post("/v1/chat/completions")
async def chat_completions(req: Request, authorization: Optional[str] = Header(default=None)):
    """Chat completions endpoint with round-robin backend selection."""
    ip = get_client_ip(req)
    enforce_rps(ip)
    require_api_key(authorization)
    
    async with proxy_acq(ip):
        payload = await req.json()
        
        # Resolve model name aliases (OpenRouter-style -> HuggingFace-style)
        if "model" in payload:
            payload["model"] = resolve_model_name(payload["model"])
        
        # Count input tokens
        input_tokens = count_chat_tokens(payload.get("messages", []))
        
        # Check quota before processing
        if not quota_manager.check_quota(ip, input_tokens):
            raise HTTPException(
                status_code=429,
                detail="Quota exceeded",
                headers={"X-Quota-Reset": quota_manager.get_reset_time(ip)}
            )
        
        # Select backend round-robin
        idx = next(_rr_chat_index)
        try:
            backend = health_check_service.get_healthy_backend("chat", idx)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        url = f"{backend}/v1/chat/completions"
        
        if payload.get("stream", False):
            # Handle streaming
            result = await stream_proxy(url, payload, "chat", req)
            
            # Record usage (approximate for streaming)
            output_tokens = 500  # Approximate
            total_tokens = input_tokens + output_tokens
            quota_manager.record_usage(ip, total_tokens)
            tokens_processed.labels(org_ip=ip, model=payload.get("model", "unknown"), type="chat").inc(total_tokens)
            
            return result
        else:
            # Cache check for non-streaming
            cache_key = cache_service.get_cache_key(payload)
            cached_result = cache_service.get(cache_key)
            if cached_result:
                quota_manager.record_usage(ip, 0)  # No tokens for cache hit
                return cached_result
            
            # Non-streaming proxy
            result = await proxy_json(url, payload, "chat")
            
            # Cache response
            cache_service.set(cache_key, result)
            
            # Record usage
            usage = result.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            quota_manager.record_usage(ip, total_tokens)
            tokens_processed.labels(org_ip=ip, model=payload.get("model", "unknown"), type="chat").inc(total_tokens)
            
            return result


@app.post("/v1/completions")
async def sql_completions(req: Request, authorization: Optional[str] = Header(default=None)):
    """Text completions endpoint for SQL generation."""
    ip = get_client_ip(req)
    enforce_rps(ip)
    require_api_key(authorization)
    
    async with proxy_acq(ip):
        payload = await req.json()
        
        # Resolve model name aliases (OpenRouter-style -> HuggingFace-style)
        if "model" in payload:
            payload["model"] = resolve_model_name(payload["model"])
        
        # Count input tokens (roughly)
        prompt = payload.get("prompt", "")
        input_tokens = len(prompt.split()) * 2  # Approximate
        
        # Check quota before processing
        if not quota_manager.check_quota(ip, input_tokens):
            raise HTTPException(
                status_code=429,
                detail="Quota exceeded",
                headers={"X-Quota-Reset": quota_manager.get_reset_time(ip)}
            )
        
        # Use text2sql backend
        try:
            backend = health_check_service.get_healthy_backend("text2sql")
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        
        url = f"{backend}/v1/completions"
        
        if payload.get("stream", False):
            # Handle streaming
            result = await stream_proxy(url, payload, "text2sql", req)
            
            # Record usage (approximate for streaming)
            output_tokens = 200  # Approximate
            total_tokens = input_tokens + output_tokens
            quota_manager.record_usage(ip, total_tokens)
            tokens_processed.labels(org_ip=ip, model=payload.get("model", "unknown"), type="text2sql").inc(total_tokens)
            
            return result
        else:
            # Non-streaming proxy
            result = await proxy_json(url, payload, "text2sql")
            
            # Record usage
            usage = result.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            quota_manager.record_usage(ip, total_tokens)
            tokens_processed.labels(org_ip=ip, model=payload.get("model", "unknown"), type="text2sql").inc(total_tokens)
            
            return result