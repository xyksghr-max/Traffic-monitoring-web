"""Result Aggregator - consumes risk assessment results and aggregates with detection data."""

from __future__ import annotations

import json
import threading
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from pathlib import Path
import sys
from collections import defaultdict

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
        
        # 添加：按 requestId 聚合多个群组的结果
        self.pending_results: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.result_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.expected_groups: Dict[str, int] = {}
        
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
        处理评估结果（聚合同一 requestId 的所有群组）
        
        Args:
            result: 单个群组的评估结果
        """
        try:
            request_id = result.get('requestId')
            camera_id = result.get('cameraId')
            group_index = result.get('groupIndex')
            
            group_risk = result.get('results', [{}])[0].get('riskLevel', 'none') if result.get('results') else 'none'
            logger.info(
                "📥 Received LLM assessment: requestId={}, cameraId={}, groupIndex={}, risk={}",
                request_id,
                camera_id,
                group_index,
                group_risk
            )
            
            if not camera_id:
                logger.warning("Assessment result missing cameraId, skipping")
                return
            
            if not request_id:
                logger.warning("Assessment result missing requestId, skipping")
                return
            
            # 1. 从 Redis 获取原始检测结果
            detection_data = self._get_detection_from_redis(request_id)
            if not detection_data:
                logger.warning(
                    "❌ Detection data not found in Redis for requestId={}, cannot aggregate",
                    request_id
                )
                # 即使没有检测数据，也尝试发布评估结果
                self._publish_single_result_without_detection(result, camera_id)
                return
            
            # 2. 获取预期的群组数量
            expected_count = len(detection_data.get('trafficGroups', []))
            logger.debug(
                "Expected {} groups for requestId={}, current group={}",
                expected_count,
                request_id,
                group_index
            )
            
            # 3. 聚合该群组的结果
            with self.result_locks[request_id]:
                self.pending_results[request_id].append(result)
                self.expected_groups[request_id] = expected_count
                
                current_count = len(self.pending_results[request_id])
                logger.debug(
                    "Collected {}/{} group results for requestId={}",
                    current_count,
                    expected_count,
                    request_id
                )
                
                # 4. 如果所有群组结果都收到了，进行聚合并发布
                if current_count >= expected_count:
                    all_results = self.pending_results.pop(request_id)
                    self.expected_groups.pop(request_id)
                    self.result_locks.pop(request_id)
                    
                    logger.info(
                        "✅ All {} group results collected for requestId={}, aggregating...",
                        expected_count,
                        request_id
                    )
                    
                    # 5. 聚合所有群组的结果
                    merged_result = self._merge_all_group_results(
                        detection_data,
                        all_results
                    )
                    
                    # 6. 缓存最新结果到 Redis
                    if self.enable_redis and self.redis_client:
                        self._cache_latest_result(camera_id, merged_result)
                    
                    # 7. 发布到 WebSocket 频道
                    if self.enable_redis and self.redis_client:
                        self._publish_to_websocket(camera_id, merged_result)
                    
                    # 8. 触发高风险告警
                    max_risk = merged_result.get('maxRiskLevel', 'none')
                    if max_risk == 'high':
                        self._trigger_alert(camera_id, merged_result)
                    
                    logger.info(
                        "✅ Aggregated and published result for camera {}, risk={}, hasDangerous={}",
                        camera_id,
                        max_risk,
                        merged_result.get('hasDangerousDriving', False)
                    )
                else:
                    logger.debug(
                        "⏳ Waiting for more results: {}/{} collected for requestId={}",
                        current_count,
                        expected_count,
                        request_id
                    )
            
        except Exception as e:
            logger.error(f"Failed to aggregate result: {e}", exc_info=True)
    
    def _merge_all_group_results(
        self,
        detection_data: Dict[str, Any],
        all_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        聚合所有群组的评估结果
        
        Args:
            detection_data: 原始检测数据
            all_results: 所有群组的LLM评估结果列表
            
        Returns:
            合并后的完整结果
        """
        # 收集所有群组的风险等级
        all_group_results = []
        max_risk = "none"
        risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        max_llm_latency = 0.0
        llm_model = ""
        
        for result in all_results:
            # 提取该群组的结果
            group_results = result.get('results', [])
            all_group_results.extend(group_results)
            
            # 更新最大风险等级
            for group_result in group_results:
                risk = group_result.get('riskLevel', 'none')
                if risk_order.get(risk, 0) > risk_order.get(max_risk, 0):
                    max_risk = risk
            
            # 提取 metadata
            metadata = result.get('metadata', {})
            latency = metadata.get('llmLatency', 0.0)
            if latency > max_llm_latency:
                max_llm_latency = latency
            if not llm_model and metadata.get('llmModel'):
                llm_model = metadata.get('llmModel', '')
        
        # 判断是否有危险驾驶（任一群组风险 != none）
        has_dangerous = max_risk != "none"
        
        logger.debug(
            "Aggregated {} group results: maxRisk={}, hasDangerous={}",
            len(all_group_results),
            max_risk,
            has_dangerous
        )
        
        # 构建最终结果
        return {
            **detection_data,
            'riskAssessment': {
                'allGroupResults': all_group_results,
                'resultCount': len(all_group_results),
                'groupCount': len(all_results),
            },
            'hasDangerousDriving': has_dangerous,
            'maxRiskLevel': max_risk,
            'llmLatency': max_llm_latency,
            'llmModel': llm_model,
        }
    
    def _publish_single_result_without_detection(
        self,
        result: Dict[str, Any],
        camera_id: int
    ):
        """
        在没有检测数据的情况下，发布单个群组的结果
        （降级处理，不推荐）
        """
        try:
            # 提取群组风险
            group_risk = result.get('results', [{}])[0].get('riskLevel', 'none') if result.get('results') else 'none'
            
            minimal_result = {
                'cameraId': camera_id,
                'timestamp': result.get('timestamp'),
                'riskAssessment': {
                    'allGroupResults': result.get('results', []),
                    'resultCount': len(result.get('results', [])),
                    'warning': 'Detection data not found, showing partial results'
                },
                'hasDangerousDriving': group_risk != 'none',
                'maxRiskLevel': group_risk,
                'llmLatency': result.get('metadata', {}).get('llmLatency', 0.0),
                'llmModel': result.get('metadata', {}).get('llmModel', ''),
            }
            
            if self.enable_redis and self.redis_client:
                self._publish_to_websocket(camera_id, minimal_result)
                logger.warning(
                    "⚠️  Published partial result without detection data: camera={}, risk={}",
                    camera_id,
                    group_risk
                )
        except Exception as e:
            logger.error(f"Failed to publish single result: {e}")
    
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
