"""Quota management service for per-organization limits."""
import time
from typing import Dict, Optional
from datetime import datetime, timezone
from app.config import settings
from app.middleware.metrics import quota_usage, quota_exceeded


class QuotaManager:
    """Manages quotas for organizations (by IP)."""
    
    def __init__(self):
        """Initialize quota manager."""
        self.usage: Dict[str, Dict] = {}
        # Structure: {org_ip: {daily_tokens: int, daily_requests: int, reset_at: timestamp}}
    
    def _get_or_create_usage(self, org_ip: str) -> Dict:
        """Get or create usage record for an organization."""
        now = time.time()
        
        if org_ip not in self.usage:
            # Create new usage record
            self.usage[org_ip] = {
                "daily_tokens": 0,
                "daily_requests": 0,
                "monthly_tokens": 0,
                "daily_reset_at": self._get_next_day_reset(),
                "monthly_reset_at": self._get_next_month_reset()
            }
        else:
            # Check if we need to reset daily counters
            if now >= self.usage[org_ip]["daily_reset_at"]:
                self.usage[org_ip]["daily_tokens"] = 0
                self.usage[org_ip]["daily_requests"] = 0
                self.usage[org_ip]["daily_reset_at"] = self._get_next_day_reset()
            
            # Check if we need to reset monthly counters
            if now >= self.usage[org_ip]["monthly_reset_at"]:
                self.usage[org_ip]["monthly_tokens"] = 0
                self.usage[org_ip]["monthly_reset_at"] = self._get_next_month_reset()
        
        return self.usage[org_ip]
    
    def _get_next_day_reset(self) -> float:
        """Get timestamp for next daily reset (midnight UTC)."""
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = tomorrow.replace(day=now.day + 1)
        return tomorrow.timestamp()
    
    def _get_next_month_reset(self) -> float:
        """Get timestamp for next monthly reset (1st of next month)."""
        now = datetime.now(timezone.utc)
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return next_month.timestamp()
    
    def check_quota(self, org_ip: str, estimated_tokens: int = 0) -> tuple[bool, Optional[str]]:
        """
        Check if organization is within quota limits.
        
        Args:
            org_ip: Organization IP address
            estimated_tokens: Estimated tokens for this request
            
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        usage = self._get_or_create_usage(org_ip)
        
        # Check daily request limit
        if usage["daily_requests"] >= settings.org_daily_request_limit:
            quota_exceeded.labels(org_ip=org_ip, quota_type="daily_requests").inc()
            return False, "Daily request limit exceeded"
        
        # Check daily token limit
        if usage["daily_tokens"] + estimated_tokens > settings.org_daily_token_limit:
            quota_exceeded.labels(org_ip=org_ip, quota_type="daily_tokens").inc()
            return False, "Daily token limit exceeded"
        
        # Check monthly token limit
        if usage["monthly_tokens"] + estimated_tokens > settings.org_monthly_token_limit:
            quota_exceeded.labels(org_ip=org_ip, quota_type="monthly_tokens").inc()
            return False, "Monthly token limit exceeded"
        
        return True, None
    
    def record_usage(self, org_ip: str, tokens_used: int):
        """
        Record token usage for an organization.
        
        Args:
            org_ip: Organization IP address
            tokens_used: Number of tokens used
        """
        usage = self._get_or_create_usage(org_ip)
        
        # Increment counters
        usage["daily_tokens"] += tokens_used
        usage["daily_requests"] += 1
        usage["monthly_tokens"] += tokens_used
        
        # Update metrics
        quota_usage.labels(org_ip=org_ip, quota_type="daily_tokens").set(usage["daily_tokens"])
        quota_usage.labels(org_ip=org_ip, quota_type="daily_requests").set(usage["daily_requests"])
        quota_usage.labels(org_ip=org_ip, quota_type="monthly_tokens").set(usage["monthly_tokens"])
    
    def get_usage(self, org_ip: str) -> Dict:
        """Get current usage for an organization."""
        usage = self._get_or_create_usage(org_ip)
        return {
            "daily_tokens": usage["daily_tokens"],
            "daily_requests": usage["daily_requests"],
            "monthly_tokens": usage["monthly_tokens"],
            "daily_limit_tokens": settings.org_daily_token_limit,
            "daily_limit_requests": settings.org_daily_request_limit,
            "monthly_limit_tokens": settings.org_monthly_token_limit,
            "daily_reset_at": datetime.fromtimestamp(usage["daily_reset_at"], tz=timezone.utc).isoformat(),
            "monthly_reset_at": datetime.fromtimestamp(usage["monthly_reset_at"], tz=timezone.utc).isoformat()
        }
    
    def get_all_usage(self) -> Dict[str, Dict]:
        """Get usage for all organizations."""
        return {org_ip: self.get_usage(org_ip) for org_ip in self.usage.keys()}


# Global quota manager instance
quota_manager = QuotaManager()
