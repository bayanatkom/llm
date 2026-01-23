"""Response caching service for performance optimization."""
import hashlib
import json
from typing import Optional, Any
from cachetools import TTLCache
from app.config import settings


class CacheService:
    """Caches responses for identical requests."""
    
    def __init__(self):
        """Initialize cache service."""
        self.cache = TTLCache(
            maxsize=settings.cache_max_size,
            ttl=settings.cache_ttl_secs
        )
    
    def _generate_cache_key(
        self,
        model: str,
        messages: list,
        temperature: float,
        max_tokens: int,
        **kwargs
    ) -> str:
        """
        Generate cache key from request parameters.
        
        Args:
            model: Model name
            messages: Chat messages
            temperature: Temperature parameter
            max_tokens: Max tokens parameter
            **kwargs: Other parameters
            
        Returns:
            Cache key string
        """
        # Create deterministic representation
        cache_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        # Sort keys for consistency
        cache_str = json.dumps(cache_data, sort_keys=True)
        
        # Hash to create key
        return hashlib.sha256(cache_str.encode()).hexdigest()
    
    def get(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Optional[Any]:
        """
        Get cached response if available.
        
        Args:
            model: Model name
            messages: Chat messages
            temperature: Temperature parameter
            max_tokens: Max tokens parameter
            **kwargs: Other parameters
            
        Returns:
            Cached response or None
        """
        # Don't cache if temperature is high (non-deterministic)
        if temperature > 0.3:
            return None
        
        key = self._generate_cache_key(model, messages, temperature, max_tokens, **kwargs)
        return self.cache.get(key)
    
    def set(
        self,
        response: Any,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ):
        """
        Cache a response.
        
        Args:
            response: Response to cache
            model: Model name
            messages: Chat messages
            temperature: Temperature parameter
            max_tokens: Max tokens parameter
            **kwargs: Other parameters
        """
        # Don't cache if temperature is high
        if temperature > 0.3:
            return
        
        key = self._generate_cache_key(model, messages, temperature, max_tokens, **kwargs)
        self.cache[key] = response
    
    def clear(self):
        """Clear all cached responses."""
        self.cache.clear()
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.cache.maxsize,
            "ttl_seconds": self.cache.ttl
        }


# Global cache service instance
cache_service = CacheService()
