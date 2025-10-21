"""Result Aggregator - consumes risk assessment results and aggregates with detection data."""

from __future__ import annotations

import json
import threading
from typing import Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
import sys

import redis
from loguru import logger

if TYPE_CHECKING:
    from redis import Redis

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from algo.kafka.base_consumer import BaseKafkaConsumer


class ResultAggregator:
    """
    结果聚合器
    
    功能：
    1. 消费风险评估结果
    2. 与原始检测结果关联
    3. 缓存到 Redis
    4. 发布到 WebSocket 频道
    5. 触发告警
    """
    
    def __init__(
        self, 
        kafka_bootstrap: str,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        redis_db: int = 0,
        enable_redis: bool = True
    ):
        """
        初始化结果聚合器
        
        Args:
            kafka_bootstrap: Kafka 服务器地址
            redis_host: Redis 主机
            redis_port: Redis 端口
            redis_db: Redis 数据库编号
            enable_redis: 是否启用 Redis
        """
        self.enable_redis = enable_redis
        self.redis_client: Optional[Redis] = None
        
        # 初始化 Redis
        if enable_redis:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # 测试连接
                self.redis_client.ping()
                logger.info(f"Redis connected: {redis_host}:{redis_port}/{redis_db}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                logger.warning("Redis functionality will be disabled")
                self.enable_redis = False
                self.redis_client = None
        
        # 初始化 Kafka 消费者
        self.consumer = BaseKafkaConsumer(
            bootstrap_servers=kafka_bootstrap,
            group_id="result-aggregator",
            topics=["risk-assessment-results"],
            message_handler=self.handle_assessment_result
        )
        
        logger.info("Result Aggregator initialized")
    
    def handle_assessment_result(self, result: Dict[str, Any]):
        """
        处理评估结果
        
        Args:
            result: 评估结果数据
        """
        try:
            request_id = result.get('requestId')
            camera_id = result.get('cameraId')
            
            logger.info(
                "📥 Received LLM assessment result: requestId={}, cameraId={}, hasDangerous={}",
                request_id,
                camera_id,
                result.get('hasDangerousDriving', False)
            )
            
            if not camera_id:
                logger.warning("Assessment result missing cameraId, skipping")
                return
            
            logger.debug(f"Processing assessment result for camera {camera_id}, request {request_id}")
            
            # 1. 从 Redis 获取原始检测结果
            detection_data = None
            if self.enable_redis and self.redis_client and request_id:
                detection_data = self._get_detection_from_redis(request_id)
            
            # 2. 合并结果
            if detection_data:
                merged_result = {
                    **detection_data,
                    'riskAssessment': result,
                    'hasDangerousDriving': result.get('hasDangerousDriving', False),
                    'maxRiskLevel': result.get('maxRiskLevel', 'none'),
                    'llmLatency': result.get('metadata', {}).get('llmLatency', 0.0),
                    'llmModel': result.get('metadata', {}).get('llmModel', ''),
                }
            else:
                # 如果没有原始数据，只使用评估结果
                merged_result = {
                    'cameraId': camera_id,
                    'timestamp': result.get('timestamp'),
                    'riskAssessment': result,
                    'hasDangerousDriving': result.get('hasDangerousDriving', False),
                    'maxRiskLevel': result.get('maxRiskLevel', 'none'),
                }
            
            # 3. 缓存最新结果到 Redis
            if self.enable_redis and self.redis_client:
                self._cache_latest_result(camera_id, merged_result)
            
            # 4. 发布到 WebSocket 频道
            max_risk = result.get('maxRiskLevel', 'none')
            if self.enable_redis and self.redis_client:
                self._publish_to_websocket(camera_id, merged_result)
                logger.info(
                    "📡 Published to WebSocket: camera={}, risk={}, hasDangerous={}",
                    camera_id,
                    max_risk,
                    merged_result.get('hasDangerousDriving', False)
                )
            
            # 5. 触发高风险告警
            if max_risk == 'high':
                self._trigger_alert(camera_id, merged_result)
            
            logger.info(
                "✅ Aggregated result for camera {}, risk={}",
                camera_id,
                max_risk
            )
            
        except Exception as e:
            logger.error(f"Failed to aggregate result: {e}", exc_info=True)
    
    def _get_detection_from_redis(self, request_id: str) -> Optional[Dict[str, Any]]:
        """从 Redis 获取检测结果"""
        try:
            detection_key = f"detection:{request_id}"
            detection_json = self.redis_client.get(detection_key)
            if detection_json:
                logger.debug(
                    "✅ Found detection data in Redis: key={}, size={} bytes",
                    detection_key,
                    len(detection_json)
                )
                return json.loads(detection_json)
            else:
                logger.warning(
                    "❌ Detection data not found in Redis: key={}, requestId={}",
                    detection_key,
                    request_id
                )
                return None
        except Exception as e:
            logger.error(f"Failed to get detection from Redis: {e}")
            return None
    
    def _cache_latest_result(self, camera_id: int, result: Dict[str, Any]):
        """缓存最新结果到 Redis"""
        try:
            camera_key = f"camera:{camera_id}:latest"
            result_json = json.dumps(result, ensure_ascii=False)
            # 设置 5 分钟过期
            self.redis_client.setex(camera_key, 300, result_json)
            logger.debug(f"Cached latest result for camera {camera_id}")
        except Exception as e:
            logger.error(f"Failed to cache result to Redis: {e}")
    
    def _publish_to_websocket(self, camera_id: int, result: Dict[str, Any]):
        """发布结果到 WebSocket 频道"""
        try:
            channel = f"camera:{camera_id}"
            result_json = json.dumps(result, ensure_ascii=False)
            subscribers = self.redis_client.publish(channel, result_json)
            logger.info(
                "📡 Published to WebSocket channel '{}': {} subscribers, risk={}, hasDangerous={}",
                channel,
                subscribers,
                result.get('maxRiskLevel', 'none'),
                result.get('hasDangerousDriving', False)
            )
        except Exception as e:
            logger.error(f"Failed to publish to WebSocket: {e}")
    
    def _trigger_alert(self, camera_id: int, result: Dict[str, Any]):
        """触发高风险告警"""
        try:
            alert_key = f"alerts:{camera_id}"
            alert_json = json.dumps(result, ensure_ascii=False)
            
            # 添加到告警列表（最多保留 100 条）
            if self.enable_redis and self.redis_client:
                self.redis_client.lpush(alert_key, alert_json)
                self.redis_client.ltrim(alert_key, 0, 99)
            
            logger.warning(f"🚨 High risk alert triggered for camera {camera_id}")
            
            # TODO: 发送告警通知（邮件、短信、Webhook 等）
            
        except Exception as e:
            logger.error(f"Failed to trigger alert: {e}")
    
    def start(self):
        """启动聚合器"""
        logger.info("Starting Result Aggregator...")
        thread = threading.Thread(target=self.consumer.start, daemon=True)
        thread.start()
        logger.success("Result Aggregator started")
        return thread
    
    def stop(self):
        """停止聚合器"""
        logger.info("Stopping Result Aggregator...")
        self.consumer.stop()
        if self.redis_client:
            self.redis_client.close()
        logger.info("Result Aggregator stopped")
