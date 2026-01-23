"""Structured logging middleware with PII redaction."""
import structlog
import uuid
import time
from fastapi import Request
from typing import Callable
from app.config import settings
from app.utils.pii_redaction import PIIRedactor


# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(structlog.stdlib, settings.log_level.upper(), structlog.stdlib.INFO)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()


async def logging_middleware(request: Request, call_next: Callable):
    """
    Middleware for structured logging with correlation IDs and PII redaction.
    """
    # Generate correlation ID
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    
    # Extract request info
    org_ip = get_client_ip(request)
    method = request.method
    path = request.url.path
    
    # Bind context for this request
    log = logger.bind(
        correlation_id=correlation_id,
        org_ip=org_ip,
        method=method,
        path=path
    )
    
    # Log request start
    start_time = time.time()
    log.info("request_started")
    
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log request completion
        log.info(
            "request_completed",
            status_code=response.status_code,
            duration_seconds=round(duration, 3)
        )
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Redact PII from error message if enabled
        error_msg = str(e)
        if settings.enable_pii_redaction:
            error_msg = PIIRedactor.redact_text(error_msg)
        
        log.error(
            "request_failed",
            error=error_msg,
            error_type=type(e).__name__,
            duration_seconds=round(duration, 3)
        )
        raise


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def get_request_logger(request: Request) -> structlog.BoundLogger:
    """Get logger with request context."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    org_ip = get_client_ip(request)
    
    return logger.bind(
        correlation_id=correlation_id,
        org_ip=org_ip
    )
