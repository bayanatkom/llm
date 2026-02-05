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
    
    def get_cache_key(self, payload: dict) -> str:
        """
        Generate cache key from request payload.
        
        Args:
            payload: Request payload dictionary
            
        Returns:
            Cache key string
        """
        return self._generate_cache_key(
            model=payload.get("model", ""),
            messages=payload.get("messages", []),
            temperature=payload.get("temperature", 0.7),
            max_tokens=payload.get("max_tokens", 2048),
            prompt=payload.get("prompt", ""),
            stop=payload.get("stop"),
            top_p=payload.get("top_p"),
        )
    
    def get(self, cache_key: str) -> Optional[Any]:
        """
        Get cached response by key.
        
        Args:
            cache_key: Cache key from get_cache_key()
            
        Returns:
            Cached response or None
        """
        return self.cache.get(cache_key)
    
    def set(self, cache_key: str, response: Any) -> None:
        """
        Cache a response by key.
        
        Args:
            cache_key: Cache key from get_cache_key()
            response: Response to cache
        """
        self.cache[cache_key] = response
    
    def should_cache(self, payload: dict) -> bool:
        """
        Check if payload should be cached (low temperature only).
        
        Args:
            payload: Request payload dictionary
            
        Returns:
            True if cacheable, False otherwise
        """
        temperature = payload.get("temperature", 0.7)
        return temperature <= 0.3
    
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
