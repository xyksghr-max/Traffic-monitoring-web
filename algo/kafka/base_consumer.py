"""Base Kafka Consumer class."""

from __future__ import annotations

import json
from typing import Callable, Dict, Any, List, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException
from loguru import logger


class BaseKafkaConsumer:
    """Kafka 消费者基类"""
    
    def __init__(
        self, 
        bootstrap_servers: str,
        group_id: str,
        topics: List[str],
        message_handler: Callable[[Dict[str, Any]], None],
        auto_commit: bool = True,
        auto_offset_reset: str = 'latest'
    ):
        """
        初始化 Kafka Consumer
        
        Args:
            bootstrap_servers: Kafka 服务器地址
            group_id: 消费组 ID
            topics: 订阅的 Topic 列表
            message_handler: 消息处理函数
            auto_commit: 是否自动提交偏移量
            auto_offset_reset: 偏移量重置策略 (latest/earliest)
        """
        self.topics = topics
        self.message_handler = message_handler
        self.running = False
        
        try:
            self.consumer = Consumer({
                'bootstrap.servers': bootstrap_servers,
                'group.id': group_id,
                'auto.offset.reset': auto_offset_reset,
                'enable.auto.commit': auto_commit,
                'auto.commit.interval.ms': 5000,
                'max.poll.records': 500,
                'session.timeout.ms': 30000,
                'heartbeat.interval.ms': 3000,
            })
            logger.info(f"Kafka Consumer initialized: group={group_id}, topics={topics}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka Consumer: {e}")
            raise
    
    def start(self):
        """启动消费者"""
        try:
            self.consumer.subscribe(self.topics)
            self.running = True
            logger.info(f"Kafka consumer started for topics: {self.topics}")
            
            while self.running:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                    
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # 到达分区末尾，继续
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        continue
                
                # 处理消息
                try:
                    data = json.loads(msg.value().decode('utf-8'))
                    self.message_handler(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON message: {e}")
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")
                    
        except KafkaException as e:
            logger.error(f"Kafka exception: {e}")
        finally:
            self.close()
    
    def stop(self):
        """停止消费者"""
        logger.info("Stopping Kafka consumer...")
        self.running = False
    
    def close(self):
        """关闭消费者"""
        if hasattr(self, 'consumer'):
            self.consumer.close()
            logger.info("Kafka Consumer closed")
