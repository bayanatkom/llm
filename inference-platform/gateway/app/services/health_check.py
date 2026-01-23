"""Health check service for backend monitoring."""
import asyncio
import httpx
from typing import Dict, List
from datetime import datetime
from app.config import settings
from app.middleware.metrics import backend_health


class HealthCheckService:
    """Monitors backend health and manages healthy backend pool."""
    
    def __init__(self):
        """Initialize health check service."""
        self.healthy_backends: Dict[str, List[str]] = {
            "chat": [],
            "text2sql": [],
            "embed": [],
            "rerank": []
        }
        self.backend_status: Dict[str, Dict] = {}
        self._running = False
        self._task = None
        
        # HTTP client for health checks
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.health_check_timeout_secs)
        )
    
    async def check_backend(self, backend_url: str, backend_type: str) -> bool:
        """
        Check if a backend is healthy.
        
        Args:
            backend_url: URL of the backend
            backend_type: Type of backend (chat, text2sql, etc.)
            
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try to hit the health endpoint
            response = await self.client.get(f"{backend_url}/health")
            is_healthy = response.status_code == 200
            
            # Update metrics
            backend_health.labels(
                backend=backend_url,
                type=backend_type
            ).set(1 if is_healthy else 0)
            
            # Update status
            self.backend_status[backend_url] = {
                "healthy": is_healthy,
                "last_check": datetime.utcnow().isoformat(),
                "type": backend_type
            }
            
            return is_healthy
        
        except Exception as e:
            # Backend is unhealthy
            backend_health.labels(
                backend=backend_url,
                type=backend_type
            ).set(0)
            
            self.backend_status[backend_url] = {
                "healthy": False,
                "last_check": datetime.utcnow().isoformat(),
                "type": backend_type,
                "error": str(e)
            }
            
            return False
    
    async def update_healthy_backends(self):
        """Update the list of healthy backends."""
        # Check chat backends
        chat_healthy = []
        for backend in settings.chat_backends:
            if await self.check_backend(backend, "chat"):
                chat_healthy.append(backend)
        self.healthy_backends["chat"] = chat_healthy
        
        # Check text2sql backend
        if await self.check_backend(settings.text2sql_backend, "text2sql"):
            self.healthy_backends["text2sql"] = [settings.text2sql_backend]
        else:
            self.healthy_backends["text2sql"] = []
        
        # Check embed backend
        if await self.check_backend(settings.embed_backend, "embed"):
            self.healthy_backends["embed"] = [settings.embed_backend]
        else:
            self.healthy_backends["embed"] = []
        
        # Check rerank backend
        if await self.check_backend(settings.rerank_backend, "rerank"):
            self.healthy_backends["rerank"] = [settings.rerank_backend]
        else:
            self.healthy_backends["rerank"] = []
    
    async def health_check_loop(self):
        """Continuous health check loop."""
        while self._running:
            try:
                await self.update_healthy_backends()
            except Exception as e:
                print(f"Health check error: {e}")
            
            # Wait before next check
            await asyncio.sleep(settings.health_check_interval_secs)
    
    async def start(self):
        """Start the health check service."""
        if not self._running:
            self._running = True
            # Do initial health check
            await self.update_healthy_backends()
            # Start background task
            self._task = asyncio.create_task(self.health_check_loop())
    
    async def stop(self):
        """Stop the health check service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()
    
    def get_healthy_backend(self, backend_type: str) -> str:
        """
        Get a healthy backend of the specified type.
        
        Args:
            backend_type: Type of backend needed
            
        Returns:
            Backend URL
            
        Raises:
            ValueError: If no healthy backends available
        """
        backends = self.healthy_backends.get(backend_type, [])
        if not backends:
            raise ValueError(f"No healthy {backend_type} backends available")
        
        # Simple round-robin (could be enhanced with load balancing)
        # For now, just return the first healthy backend
        return backends[0]
    
    def get_all_status(self) -> Dict:
        """Get status of all backends."""
        return {
            "healthy_backends": self.healthy_backends,
            "backend_status": self.backend_status
        }


# Global health check service instance
health_check_service = HealthCheckService()
