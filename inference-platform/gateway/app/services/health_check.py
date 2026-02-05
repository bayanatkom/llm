"""Health check service for monitoring backend health."""
import asyncio
from typing import Dict, List, Optional
import httpx

from app.config import settings
from app.middleware.circuit_breaker import circuit_breaker_manager


class HealthCheckService:
    """Service for checking backend health periodically."""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.health_check_timeout_secs)
        self.healthy_backends: Dict[str, List[str]] = {
            "chat": [],
            "text2sql": []
        }
        self.check_task: Optional[asyncio.Task] = None
    
    async def check_backend(self, url: str, backend_type: str) -> bool:
        """Check if a backend is healthy."""
        try:
            headers = {"Authorization": f"Bearer {settings.backend_api_key}"}
            response = await self.client.get(f"{url}/health", headers=headers)
            return response.status_code == 200
        except Exception:
            return False
    
    async def periodic_check(self):
        """Periodic health check loop."""
        while True:
            await self.check_all_backends()
            await asyncio.sleep(settings.health_check_interval_secs)
    
    async def check_all_backends(self):
        """Check all configured backends."""
        # Check chat backends
        healthy_chat = []
        for backend in settings.get_chat_backends():
            if await self.check_backend(backend, "chat"):
                healthy_chat.append(backend)
        self.healthy_backends["chat"] = healthy_chat
        
        # Check text2sql backend
        if await self.check_backend(settings.text2sql_backend, "text2sql"):
            self.healthy_backends["text2sql"] = [settings.text2sql_backend]
        else:
            self.healthy_backends["text2sql"] = []
    
    def get_healthy_backend(self, backend_type: str, index: int = 0) -> str:
        """Get a healthy backend URL.
        
        Args:
            backend_type: Type of backend (chat, text2sql)
            index: Index for round-robin selection (chat only)
            
        Returns:
            Healthy backend URL
            
        Raises:
            ValueError: If no healthy backends available
        """
        backends = self.healthy_backends.get(backend_type, [])
        if not backends:
            raise ValueError(f"No healthy {backend_type} backends available")
        
        if backend_type == "chat" and len(backends) > 1:
            # Use round-robin for chat
            return backends[index % len(backends)]
        
        return backends[0]
    
    def get_status(self) -> Dict[str, List[str]]:
        """Get current backend health status."""
        return self.healthy_backends.copy()
    
    async def start(self):
        """Start health check service."""
        # Initial check
        await self.check_all_backends()
        # Start periodic checks
        self.check_task = asyncio.create_task(self.periodic_check())
    
    async def stop(self):
        """Stop health check service."""
        if self.check_task:
            self.check_task.cancel()
            try:
                await self.check_task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()


# Global instance
health_check_service = HealthCheckService()