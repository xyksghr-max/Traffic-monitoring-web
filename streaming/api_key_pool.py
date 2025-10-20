"""API Key pool manager for distributed LLM API calls."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from loguru import logger


class KeyStatus(str, Enum):
    """API Key status enumeration."""
    AVAILABLE = "available"
    IN_USE = "in_use"
    COOLING = "cooling"
    DISABLED = "disabled"


@dataclass
class APIKeyInfo:
    """Information about an API key."""
    key_id: str = field(default_factory=lambda: str(uuid4()))
    api_key: str = ""
    status: KeyStatus = KeyStatus.AVAILABLE
    
    # Usage statistics
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    rate_limit_errors: int = 0
    
    # Timing information
    last_call_time: float = 0.0
    cooldown_until: float = 0.0
    created_at: float = field(default_factory=time.time)
    
    # Rate limiting
    qps_limit: int = 5  # Queries per second
    rpm_limit: int = 100  # Requests per minute
    daily_limit: Optional[int] = None  # Optional daily quota
    
    # Current load
    current_calls: int = 0  # In-flight requests
    
    # Metadata
    name: Optional[str] = None
    provider: str = "dashscope"
    model: str = "qwen-vl-plus"
    cost_per_call: float = 0.0
    priority: int = 1  # Higher priority keys are preferred
    
    def is_available(self, now: Optional[float] = None) -> bool:
        """Check if the key is currently available."""
        if now is None:
            now = time.time()
        
        if self.status == KeyStatus.DISABLED:
            return False
        
        if self.status == KeyStatus.COOLING and now < self.cooldown_until:
            return False
        
        # Check if cooling period expired
        if self.status == KeyStatus.COOLING and now >= self.cooldown_until:
            self.status = KeyStatus.AVAILABLE
        
        return self.status in (KeyStatus.AVAILABLE, KeyStatus.IN_USE)
    
    def can_accept_call(self, now: Optional[float] = None) -> bool:
        """Check if key can accept a new call based on rate limits."""
        if not self.is_available(now):
            return False
        
        # Simple check: if current calls exceed QPS, reject
        if self.current_calls >= self.qps_limit:
            return False
        
        return True
    
    def mark_in_use(self) -> None:
        """Mark key as in use."""
        self.status = KeyStatus.IN_USE
        self.current_calls += 1
        self.last_call_time = time.time()
    
    def mark_success(self) -> None:
        """Mark a successful API call."""
        self.total_calls += 1
        self.success_calls += 1
        self.current_calls = max(0, self.current_calls - 1)
        if self.current_calls == 0:
            self.status = KeyStatus.AVAILABLE
    
    def mark_failed(self, is_rate_limit: bool = False) -> None:
        """Mark a failed API call."""
        self.total_calls += 1
        self.failed_calls += 1
        self.current_calls = max(0, self.current_calls - 1)
        
        if is_rate_limit:
            self.rate_limit_errors += 1
        
        if self.current_calls == 0:
            self.status = KeyStatus.AVAILABLE
    
    def start_cooling(self, cooldown_seconds: float = 60.0) -> None:
        """Put the key into cooling state."""
        self.status = KeyStatus.COOLING
        self.cooldown_until = time.time() + cooldown_seconds
        logger.warning(
            f"API Key {self.key_id[:8]}... entering cooling state for {cooldown_seconds}s"
        )
    
    def disable(self, reason: str = "Unknown") -> None:
        """Disable the key."""
        self.status = KeyStatus.DISABLED
        logger.error(f"API Key {self.key_id[:8]}... disabled. Reason: {reason}")
    
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_calls == 0:
            return 1.0
        return self.success_calls / self.total_calls
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for monitoring."""
        return {
            "key_id": self.key_id,
            "name": self.name,
            "status": self.status.value,
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "rate_limit_errors": self.rate_limit_errors,
            "success_rate": self.success_rate(),
            "current_calls": self.current_calls,
            "qps_limit": self.qps_limit,
            "cooldown_until": self.cooldown_until if self.status == KeyStatus.COOLING else None,
        }


class APIKeyPool:
    """Pool manager for multiple API keys with load balancing and fault tolerance."""
    
    def __init__(
        self,
        keys: Optional[List[APIKeyInfo]] = None,
        strategy: str = "round_robin",  # round_robin, least_loaded, priority
        max_retry_per_key: int = 3,
        default_cooldown: float = 60.0,
    ) -> None:
        """Initialize the API key pool.
        
        Args:
            keys: List of API key information
            strategy: Load balancing strategy
            max_retry_per_key: Max failed attempts before disabling
            default_cooldown: Default cooldown period in seconds
        """
        self._keys: Dict[str, APIKeyInfo] = {}
        self._lock = asyncio.Lock()
        self._round_robin_index = 0
        self._strategy = strategy
        self._max_retry_per_key = max_retry_per_key
        self._default_cooldown = default_cooldown
        
        if keys:
            for key in keys:
                self._keys[key.key_id] = key
        
        logger.info(f"APIKeyPool initialized with {len(self._keys)} keys using {strategy} strategy")
    
    async def add_key(self, key_info: APIKeyInfo) -> None:
        """Add a new key to the pool."""
        async with self._lock:
            self._keys[key_info.key_id] = key_info
            logger.info(f"Added API Key {key_info.key_id[:8]}... to pool")
    
    async def remove_key(self, key_id: str) -> bool:
        """Remove a key from the pool."""
        async with self._lock:
            if key_id in self._keys:
                del self._keys[key_id]
                logger.info(f"Removed API Key {key_id[:8]}... from pool")
                return True
            return False
    
    async def get_key_stats(self) -> List[Dict]:
        """Get statistics for all keys."""
        async with self._lock:
            return [key.to_dict() for key in self._keys.values()]
    
    async def acquire_key(self, timeout: float = 10.0) -> Optional[APIKeyInfo]:
        """Acquire an available API key from the pool.
        
        Args:
            timeout: Maximum time to wait for an available key
            
        Returns:
            APIKeyInfo if successful, None if no key available within timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            async with self._lock:
                key = self._select_key()
                if key:
                    key.mark_in_use()
                    logger.debug(f"Acquired key {key.key_id[:8]}... (strategy: {self._strategy})")
                    return key
            
            # No key available, wait a bit
            await asyncio.sleep(0.1)
        
        logger.warning(f"Failed to acquire key within {timeout}s timeout")
        return None
    
    def _select_key(self) -> Optional[APIKeyInfo]:
        """Select a key based on the configured strategy."""
        now = time.time()
        available_keys = [
            key for key in self._keys.values()
            if key.can_accept_call(now)
        ]
        
        if not available_keys:
            return None
        
        if self._strategy == "round_robin":
            return self._select_round_robin(available_keys)
        elif self._strategy == "least_loaded":
            return self._select_least_loaded(available_keys)
        elif self._strategy == "priority":
            return self._select_priority(available_keys)
        else:
            # Default to round robin
            return self._select_round_robin(available_keys)
    
    def _select_round_robin(self, keys: List[APIKeyInfo]) -> APIKeyInfo:
        """Round-robin selection."""
        self._round_robin_index = (self._round_robin_index + 1) % len(keys)
        return keys[self._round_robin_index]
    
    def _select_least_loaded(self, keys: List[APIKeyInfo]) -> APIKeyInfo:
        """Select the key with the least current load."""
        return min(keys, key=lambda k: k.current_calls)
    
    def _select_priority(self, keys: List[APIKeyInfo]) -> APIKeyInfo:
        """Select the highest priority available key."""
        return max(keys, key=lambda k: k.priority)
    
    async def release_key(
        self,
        key: APIKeyInfo,
        success: bool = True,
        is_rate_limit: bool = False,
    ) -> None:
        """Release a key back to the pool after use.
        
        Args:
            key: The key to release
            success: Whether the API call was successful
            is_rate_limit: Whether the failure was due to rate limiting
        """
        async with self._lock:
            if success:
                key.mark_success()
                logger.debug(f"Released key {key.key_id[:8]}... (success)")
            else:
                key.mark_failed(is_rate_limit=is_rate_limit)
                logger.warning(f"Released key {key.key_id[:8]}... (failed)")
                
                # Handle rate limit errors
                if is_rate_limit:
                    key.start_cooling(self._default_cooldown)
                
                # Disable key if too many failures
                consecutive_failures = key.failed_calls - key.success_calls
                if consecutive_failures >= self._max_retry_per_key:
                    key.disable(f"Too many consecutive failures: {consecutive_failures}")
    
    async def get_available_count(self) -> int:
        """Get the number of currently available keys."""
        async with self._lock:
            now = time.time()
            return sum(1 for key in self._keys.values() if key.can_accept_call(now))
    
    async def get_total_capacity(self) -> int:
        """Get the total theoretical QPS capacity of the pool."""
        async with self._lock:
            return sum(key.qps_limit for key in self._keys.values() if key.is_available())
    
    async def health_check(self) -> Dict:
        """Perform a health check on the pool."""
        async with self._lock:
            now = time.time()
            available = [k for k in self._keys.values() if k.can_accept_call(now)]
            in_use = [k for k in self._keys.values() if k.status == KeyStatus.IN_USE]
            cooling = [k for k in self._keys.values() if k.status == KeyStatus.COOLING]
            disabled = [k for k in self._keys.values() if k.status == KeyStatus.DISABLED]
            
            total_calls = sum(k.total_calls for k in self._keys.values())
            total_success = sum(k.success_calls for k in self._keys.values())
            
            return {
                "total_keys": len(self._keys),
                "available_keys": len(available),
                "in_use_keys": len(in_use),
                "cooling_keys": len(cooling),
                "disabled_keys": len(disabled),
                "total_capacity_qps": sum(k.qps_limit for k in self._keys.values()),
                "available_capacity_qps": sum(k.qps_limit for k in available),
                "total_calls": total_calls,
                "total_success": total_success,
                "overall_success_rate": total_success / total_calls if total_calls > 0 else 1.0,
                "strategy": self._strategy,
            }


def create_key_pool_from_config(config: Dict) -> APIKeyPool:
    """Create an API key pool from configuration dictionary.
    
    Example config:
    {
        "strategy": "round_robin",
        "max_retry_per_key": 3,
        "default_cooldown": 60.0,
        "keys": [
            {
                "api_key": "sk-xxx",
                "name": "key-001",
                "qps_limit": 5,
                "rpm_limit": 100
            },
            ...
        ]
    }
    """
    keys = []
    for key_config in config.get("keys", []):
        key_info = APIKeyInfo(
            api_key=key_config["api_key"],
            name=key_config.get("name"),
            qps_limit=key_config.get("qps_limit", 5),
            rpm_limit=key_config.get("rpm_limit", 100),
            priority=key_config.get("priority", 1),
            model=key_config.get("model", "qwen-vl-plus"),
        )
        keys.append(key_info)
    
    return APIKeyPool(
        keys=keys,
        strategy=config.get("strategy", "round_robin"),
        max_retry_per_key=config.get("max_retry_per_key", 3),
        default_cooldown=config.get("default_cooldown", 60.0),
    )
