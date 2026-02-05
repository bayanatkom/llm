"""Circuit breaker implementation for backend resilience."""
import time
from typing import Dict, Callable, Any
from enum import Enum
import asyncio
from app.config import settings
from app.middleware.metrics import circuit_breaker_state, circuit_breaker_failures


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = 0      # Normal operation
    OPEN = 1        # Failing, reject requests
    HALF_OPEN = 2   # Testing if backend recovered


class CircuitBreaker:
    """Circuit breaker for a single backend."""
    
    def __init__(
        self,
        backend_name: str,
        failure_threshold: int = None,
        recovery_timeout: int = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            backend_name: Name of the backend
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying again
        """
        self.backend_name = backend_name
        self.failure_threshold = failure_threshold or settings.circuit_failure_threshold
        self.recovery_timeout = recovery_timeout or settings.circuit_recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.success_count = 0
        
        # Update metric
        circuit_breaker_state.labels(backend=backend_name).set(self.state.value)
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return (
            self.state == CircuitState.OPEN and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _record_success(self):
        """Record successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            # After 3 successful calls in half-open, close the circuit
            if self.success_count >= 3:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                circuit_breaker_state.labels(backend=self.backend_name).set(self.state.value)
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def _record_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        circuit_breaker_failures.labels(backend=self.backend_name).inc()
        
        if self.state == CircuitState.HALF_OPEN:
            # Failed during recovery, go back to open
            self.state = CircuitState.OPEN
            self.success_count = 0
            circuit_breaker_state.labels(backend=self.backend_name).set(self.state.value)
        
        elif self.state == CircuitState.CLOSED:
            # Check if we should open the circuit
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                circuit_breaker_state.labels(backend=self.backend_name).set(self.state.value)
    
    def __enter__(self) -> "CircuitBreaker":
        """
        Enter context manager - check circuit state.
        
        Returns:
            Self for context manager usage
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self.state = CircuitState.HALF_OPEN
            self.success_count = 0
            circuit_breaker_state.labels(backend=self.backend_name).set(self.state.value)
        
        # Reject if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker open for {self.backend_name}"
            )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Exit context manager - record success or failure.
        
        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised
            
        Returns:
            False to propagate exceptions
        """
        if exc_type is None:
            # No exception, record success
            self._record_success()
        else:
            # Exception occurred, record failure
            self._record_failure()
        
        # Don't suppress exceptions
        return False
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self.state = CircuitState.HALF_OPEN
            self.success_count = 0
            circuit_breaker_state.labels(backend=self.backend_name).set(self.state.value)
        
        # Reject if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker open for {self.backend_name}"
            )
        
        # Attempt the call
        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreakerManager:
    """Manages circuit breakers for all backends."""
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, backend_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for backend."""
        if backend_name not in self._breakers:
            self._breakers[backend_name] = CircuitBreaker(backend_name)
        return self._breakers[backend_name]
    
    async def call(self, backend_name: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        breaker = self.get_breaker(backend_name)
        return await breaker.call(func, *args, **kwargs)
    
    def get_state(self, backend_name: str) -> CircuitState:
        """Get circuit breaker state for backend."""
        if backend_name in self._breakers:
            return self._breakers[backend_name].state
        return CircuitState.CLOSED


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()
