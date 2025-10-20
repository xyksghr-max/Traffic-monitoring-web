"""API Key Pool Management for rate limit bypass."""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from collections import deque

from loguru import logger


class KeyStatus(Enum):
    """API Key 状态枚举"""
    AVAILABLE = "available"      # 可用
    IN_USE = "in_use"            # 使用中
    COOLING = "cooling"          # 冷却中
    DISABLED = "disabled"        # 已禁用


@dataclass
class APIKey:
    """API Key 数据类"""
    key: str
    key_id: str
    status: KeyStatus = KeyStatus.AVAILABLE
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    last_used_at: float = 0.0
    cooldown_until: float = 0.0
    qps_limit: int = 10
    rpm_limit: int = 300
    priority: int = 1
    enabled: bool = True
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.enabled:
            self.status = KeyStatus.DISABLED
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_calls == 0:
            return 1.0
        return self.success_calls / self.total_calls
    
    @property
    def is_available(self) -> bool:
        """是否可用"""
        return (
            self.enabled and
            self.status == KeyStatus.AVAILABLE and
            time.time() >= self.cooldown_until
        )


class APIKeyPool:
    """
    API Key 池管理器
    
    功能：
    1. 管理多个 API Key
    2. 负载均衡调度
    3. 失败自动切换
    4. 自适应冷却
    """
    
    def __init__(
        self,
        keys: List[dict],
        cooldown_seconds: float = 60.0,
        adaptive_cooldown: bool = True,
        min_cooldown: float = 10.0,
        max_cooldown: float = 120.0
    ):
        """
        初始化 API Key 池
        
        Args:
            keys: Key 配置列表
            cooldown_seconds: 默认冷却时间（秒）
            adaptive_cooldown: 是否启用自适应冷却
            min_cooldown: 最小冷却时间
            max_cooldown: 最大冷却时间
        """
        self.cooldown_seconds = cooldown_seconds
        self.adaptive_cooldown = adaptive_cooldown
        self.min_cooldown = min_cooldown
        self.max_cooldown = max_cooldown
        self.lock = threading.RLock()
        self.call_history = deque(maxlen=1000)
        
        # 初始化 Keys
        self.keys: List[APIKey] = []
        for key_config in keys:
            api_key = APIKey(
                key=key_config['key'],
                key_id=key_config.get('key_id', f"key_{len(self.keys) + 1}"),
                qps_limit=key_config.get('qps_limit', 10),
                rpm_limit=key_config.get('rpm_limit', 300),
                priority=key_config.get('priority', 1),
                enabled=key_config.get('enabled', True)
            )
            self.keys.append(api_key)
        
        enabled_count = sum(1 for k in self.keys if k.enabled)
        logger.info(f"API Key Pool initialized with {len(self.keys)} keys ({enabled_count} enabled)")
    
    def acquire_key(self, timeout: float = 5.0, strategy: str = 'least_loaded') -> Optional[APIKey]:
        """
        获取一个可用的 API Key
        
        Args:
            timeout: 超时时间（秒）
            strategy: 调度策略
                - 'round_robin': 轮询
                - 'least_loaded': 选择调用次数最少的
                - 'weighted': 根据优先级加权选择
                
        Returns:
            可用的 APIKey 或 None
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self.lock:
                # 检查冷却完成的 Keys
                self._update_cooling_keys()
                
                # 获取可用的 Keys
                available_keys = [k for k in self.keys if k.is_available]
                
                if not available_keys:
                    # 没有可用 Key，短暂等待后重试
                    time.sleep(0.1)
                    continue
                
                # 根据策略选择 Key
                if strategy == 'round_robin':
                    selected_key = available_keys[0]
                elif strategy == 'weighted':
                    selected_key = self._select_weighted_key(available_keys)
                else:  # least_loaded (default)
                    selected_key = min(available_keys, key=lambda k: k.total_calls)
                
                # 标记为使用中
                selected_key.status = KeyStatus.IN_USE
                selected_key.last_used_at = time.time()
                
                logger.debug(f"Acquired API key: {selected_key.key_id} (calls={selected_key.total_calls})")
                return selected_key
        
        logger.warning(f"Failed to acquire API key within {timeout}s timeout")
        return None
    
    def release_key(self, key: APIKey, success: bool = True, adaptive: bool = True):
        """
        释放 API Key
        
        Args:
            key: 要释放的 Key
            success: 调用是否成功
            adaptive: 是否使用自适应冷却
        """
        with self.lock:
            key.total_calls += 1
            
            if success:
                key.success_calls += 1
                key.status = KeyStatus.AVAILABLE
                logger.debug(f"Released API key: {key.key_id} (success)")
            else:
                key.failed_calls += 1
                key.status = KeyStatus.COOLING
                
                # 计算冷却时间
                if adaptive and self.adaptive_cooldown:
                    cooldown = self._calculate_adaptive_cooldown(key)
                else:
                    cooldown = self.cooldown_seconds
                
                key.cooldown_until = time.time() + cooldown
                logger.warning(
                    f"API key {key.key_id} entered cooling period "
                    f"({cooldown:.1f}s, success_rate={key.success_rate:.2%})"
                )
            
            # 记录调用历史
            self.call_history.append({
                'key_id': key.key_id,
                'timestamp': time.time(),
                'success': success
            })
    
    def _update_cooling_keys(self):
        """更新冷却中的 Keys 状态"""
        now = time.time()
        for key in self.keys:
            if key.status == KeyStatus.COOLING and now >= key.cooldown_until:
                key.status = KeyStatus.AVAILABLE
                logger.info(f"API key {key.key_id} cooling completed, now available")
    
    def _calculate_adaptive_cooldown(self, key: APIKey) -> float:
        """
        计算自适应冷却时间
        
        失败率越高，冷却时间越长
        """
        failure_rate = 1.0 - key.success_rate
        
        # 冷却时间 = min_cooldown + (max_cooldown - min_cooldown) * failure_rate
        cooldown = self.min_cooldown + (self.max_cooldown - self.min_cooldown) * failure_rate
        
        return min(max(cooldown, self.min_cooldown), self.max_cooldown)
    
    def _select_weighted_key(self, available_keys: List[APIKey]) -> APIKey:
        """根据优先级加权选择 Key"""
        # 优先级越高，权重越大
        total_weight = sum(k.priority for k in available_keys)
        if total_weight == 0:
            return available_keys[0]
        
        # 简化版：选择优先级最高且调用最少的
        return min(
            available_keys,
            key=lambda k: (k.total_calls / max(k.priority, 1))
        )
    
    def get_stats(self) -> dict:
        """获取池统计信息"""
        with self.lock:
            total_calls = sum(k.total_calls for k in self.keys)
            success_calls = sum(k.success_calls for k in self.keys)
            
            return {
                'total_keys': len(self.keys),
                'available_keys': sum(1 for k in self.keys if k.status == KeyStatus.AVAILABLE),
                'in_use_keys': sum(1 for k in self.keys if k.status == KeyStatus.IN_USE),
                'cooling_keys': sum(1 for k in self.keys if k.status == KeyStatus.COOLING),
                'disabled_keys': sum(1 for k in self.keys if k.status == KeyStatus.DISABLED),
                'total_calls': total_calls,
                'success_rate': success_calls / max(total_calls, 1),
                'keys': [
                    {
                        'key_id': k.key_id,
                        'status': k.status.value,
                        'total_calls': k.total_calls,
                        'success_calls': k.success_calls,
                        'failed_calls': k.failed_calls,
                        'success_rate': k.success_rate,
                        'last_used_at': k.last_used_at,
                        'cooldown_until': k.cooldown_until if k.status == KeyStatus.COOLING else None,
                    }
                    for k in self.keys
                ]
            }
    
    def disable_key(self, key_id: str):
        """禁用指定的 Key"""
        with self.lock:
            for key in self.keys:
                if key.key_id == key_id:
                    key.enabled = False
                    key.status = KeyStatus.DISABLED
                    logger.warning(f"API key {key_id} has been disabled")
                    return
    
    def enable_key(self, key_id: str):
        """启用指定的 Key"""
        with self.lock:
            for key in self.keys:
                if key.key_id == key_id:
                    key.enabled = True
                    key.status = KeyStatus.AVAILABLE
                    logger.info(f"API key {key_id} has been enabled")
                    return
