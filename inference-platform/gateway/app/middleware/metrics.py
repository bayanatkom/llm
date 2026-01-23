"""Prometheus metrics for monitoring."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from fastapi.responses import Response as FastAPIResponse
import time


# Request metrics
request_count = Counter(
    'gateway_requests_total',
    'Total number of requests',
    ['endpoint', 'method', 'status']
)

request_duration = Histogram(
    'gateway_request_duration_seconds',
    'Request duration in seconds',
    ['endpoint', 'method'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)

# Queue metrics
queue_depth = Gauge(
    'gateway_queue_depth',
    'Current queue depth per organization IP',
    ['org_ip']
)

queue_wait_time = Histogram(
    'gateway_queue_wait_seconds',
    'Time spent waiting in queue',
    ['org_ip'],
    buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Rate limiting metrics
rate_limit_rejections = Counter(
    'gateway_rate_limit_rejections_total',
    'Number of requests rejected due to rate limiting',
    ['org_ip', 'reason']
)

# Backend metrics
backend_health = Gauge(
    'gateway_backend_health',
    'Backend health status (1=healthy, 0=unhealthy)',
    ['backend', 'type']
)

backend_requests = Counter(
    'gateway_backend_requests_total',
    'Total requests to backends',
    ['backend', 'type', 'status']
)

backend_duration = Histogram(
    'gateway_backend_duration_seconds',
    'Backend request duration',
    ['backend', 'type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Active requests
active_requests = Gauge(
    'gateway_active_requests',
    'Number of currently active requests',
    ['org_ip']
)

# Token usage
tokens_processed = Counter(
    'gateway_tokens_processed_total',
    'Total tokens processed',
    ['org_ip', 'model', 'type']  # type: prompt or completion
)

# Quota metrics
quota_usage = Gauge(
    'gateway_quota_usage',
    'Current quota usage',
    ['org_ip', 'quota_type']  # quota_type: daily_tokens, daily_requests, etc.
)

quota_exceeded = Counter(
    'gateway_quota_exceeded_total',
    'Number of requests rejected due to quota',
    ['org_ip', 'quota_type']
)

# Circuit breaker metrics
circuit_breaker_state = Gauge(
    'gateway_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['backend']
)

circuit_breaker_failures = Counter(
    'gateway_circuit_breaker_failures_total',
    'Circuit breaker failure count',
    ['backend']
)


async def metrics_middleware(request: Request, call_next):
    """Middleware to track request metrics."""
    start_time = time.time()
    
    # Track active requests
    org_ip = get_client_ip(request)
    active_requests.labels(org_ip=org_ip).inc()
    
    try:
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        endpoint = request.url.path
        method = request.method
        status = response.status_code
        
        request_count.labels(
            endpoint=endpoint,
            method=method,
            status=status
        ).inc()
        
        request_duration.labels(
            endpoint=endpoint,
            method=method
        ).observe(duration)
        
        return response
    
    finally:
        active_requests.labels(org_ip=org_ip).dec()


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def metrics_endpoint(request: Request) -> FastAPIResponse:
    """Endpoint to expose Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
