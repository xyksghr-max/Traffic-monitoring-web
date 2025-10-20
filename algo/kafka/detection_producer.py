"""Kafka Producer for detection results."""

from __future__ import annotations

import json
import uuid
from typing import Dict, Any, Optional

from confluent_kafka import Producer
from loguru import logger


class DetectionResultProducer:
    """发送检测结果到 Kafka Topic"""
    
    def __init__(self, bootstrap_servers: str, topic: str, enable_kafka: bool = True):
        """
        初始化 Kafka Producer
        
        Args:
            bootstrap_servers: Kafka 服务器地址
            topic: Topic 名称
            enable_kafka: 是否启用 Kafka (用于降级开关)
        """
        self.topic = topic
        self.enable_kafka = enable_kafka
        self.producer: Optional[Producer] = None
        
        if not enable_kafka:
            logger.warning("Kafka Producer is disabled via configuration")
            return
        
        try:
            self.producer = Producer({
                'bootstrap.servers': bootstrap_servers,
                'compression.type': 'snappy',
                'linger.ms': 10,  # 批处理延迟 10ms
                'batch.size': 32768,  # 32KB 批处理大小
                'acks': 'all',  # 等待所有副本确认（幂等性要求）
                'retries': 3,  # 重试 3 次
                'retry.backoff.ms': 100,
                'enable.idempotence': True,  # 幂等性
            })
            logger.info(f"Kafka Producer initialized for topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka Producer: {e}")
            self.enable_kafka = False
    
    def send(self, detection_result: Dict[str, Any], camera_id: int) -> Optional[str]:
        """
        发送检测结果到 Kafka
        
        Args:
            detection_result: 检测结果数据
            camera_id: 摄像头 ID
            
        Returns:
            消息 ID (如果发送成功)
        """
        if not self.enable_kafka or not self.producer:
            logger.debug("Kafka is disabled, skipping message send")
            return None
        
        try:
            # 生成消息 ID
            message_id = str(uuid.uuid4())
            detection_result['messageId'] = message_id
            
            # 使用 camera_id 作为 key，确保同一摄像头的消息发送到同一分区
            key = str(camera_id).encode('utf-8')
            value = json.dumps(detection_result, ensure_ascii=False).encode('utf-8')
            
            # 异步发送
            self.producer.produce(
                topic=self.topic,
                key=key,
                value=value,
                callback=lambda err, msg: self._delivery_callback(err, msg, message_id)
            )
            
            # 非阻塞 poll
            self.producer.poll(0)
            
            logger.debug(f"Detection result sent to Kafka: messageId={message_id}, camera={camera_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to produce message to Kafka: {e}")
            return None
    
    def _delivery_callback(self, err, msg, message_id: str):
        """消息发送回调"""
        if err:
            logger.error(f"Message delivery failed for {message_id}: {err}")
        else:
            logger.debug(
                f"Message delivered: topic={msg.topic()}, "
                f"partition={msg.partition()}, offset={msg.offset()}"
            )
    
    def flush(self, timeout: float = 10.0):
        """等待所有消息发送完成"""
        if self.producer:
            remaining = self.producer.flush(timeout)
            if remaining > 0:
                logger.warning(f"{remaining} messages were not delivered before timeout")
            else:
                logger.debug("All messages flushed successfully")
    
    def close(self):
        """关闭 Producer"""
        if self.producer:
            self.flush()
            logger.info("Kafka Producer closed")
