#!/usr/bin/env python3
"""测试流处理管道的端到端流程"""

import sys
import time
import json
import argparse
from pathlib import Path
from typing import Dict, Any

from loguru import logger
from confluent_kafka import Consumer, KafkaError

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from algo.kafka.detection_producer import DetectionResultProducer


def create_mock_detection_result(camera_id: int = 1) -> Dict[str, Any]:
    """创建模拟检测结果"""
    return {
        'cameraId': camera_id,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'imageWidth': 1920,
        'imageHeight': 1080,
        'detectedObjects': [
            {
                'objectId': 1,
                'class': 'car',
                'confidence': 0.92,
                'bbox': [120, 200, 360, 520]
            },
            {
                'objectId': 2,
                'class': 'car',
                'confidence': 0.88,
                'bbox': [400, 210, 640, 530]
            },
            {
                'objectId': 3,
                'class': 'person',
                'confidence': 0.85,
                'bbox': [450, 250, 500, 450]
            }
        ],
        'trafficGroups': [
            {
                'groupIndex': 1,
                'objectCount': 3,
                'bbox': [120, 200, 640, 530],
                'classes': ['car', 'person'],
                'averageConfidence': 0.88,
                'memberIndices': [0, 1, 2]
            }
        ],
        'groupImages': [
            {
                'groupIndex': 1,
                'imageBase64': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD...',  # 简化的假数据
                'bbox': [120, 200, 640, 530],
                'objectCount': 3,
                'classes': ['car', 'person']
            }
        ]
    }


def test_kafka_producer(kafka_bootstrap: str, num_messages: int = 5):
    """测试 Kafka Producer"""
    logger.info("=== Testing Kafka Producer ===")
    
    producer = DetectionResultProducer(
        bootstrap_servers=kafka_bootstrap,
        topic="detection-results"
    )
    
    for i in range(num_messages):
        detection = create_mock_detection_result(camera_id=1)
        message_id = producer.send(detection, camera_id=1)
        if message_id:
            logger.success(f"[{i+1}/{num_messages}] Message sent: {message_id}")
        else:
            logger.error(f"[{i+1}/{num_messages}] Failed to send message")
        time.sleep(1)
    
    producer.flush()
    logger.info("=== Kafka Producer test completed ===")


def test_kafka_consumer(kafka_bootstrap: str, topic: str, timeout: int = 30):
    """测试 Kafka Consumer"""
    logger.info(f"=== Testing Kafka Consumer (topic: {topic}) ===")
    
    consumer = Consumer({
        'bootstrap.servers': kafka_bootstrap,
        'group.id': f'test-consumer-{int(time.time())}',
        'auto.offset.reset': 'latest',
    })
    
    consumer.subscribe([topic])
    logger.info(f"Subscribed to topic: {topic}")
    logger.info(f"Waiting for messages (timeout: {timeout}s)...")
    
    start_time = time.time()
    message_count = 0
    
    try:
        while time.time() - start_time < timeout:
            msg = consumer.poll(timeout=1.0)
            
            if msg is None:
                continue
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
            
            message_count += 1
            data = json.loads(msg.value().decode('utf-8'))
            
            logger.success(f"[Message {message_count}] Received from {topic}:")
            logger.info(f"  - Camera ID: {data.get('cameraId')}")
            logger.info(f"  - Timestamp: {data.get('timestamp')}")
            
            if topic == "assessment-tasks":
                logger.info(f"  - Task ID: {data.get('taskId')}")
                logger.info(f"  - Group Index: {data.get('groupIndex')}")
            elif topic == "risk-assessment-results":
                logger.info(f"  - Risk Level: {data.get('maxRiskLevel')}")
                logger.info(f"  - Has Dangerous: {data.get('hasDangerousDriving')}")
            
            logger.info("---")
    
    except KeyboardInterrupt:
        logger.info("Consumer interrupted by user")
    
    finally:
        consumer.close()
        logger.info(f"=== Received {message_count} messages from {topic} ===")


def test_end_to_end(kafka_bootstrap: str, duration: int = 60):
    """端到端测试"""
    logger.info("=== Starting End-to-End Test ===")
    logger.info(f"Duration: {duration} seconds")
    logger.info("")
    
    # 1. 发送检测结果
    logger.info("Step 1: Sending detection results...")
    test_kafka_producer(kafka_bootstrap, num_messages=3)
    
    # 2. 等待任务生成
    logger.info("")
    logger.info("Step 2: Waiting for task generation (15s)...")
    time.sleep(15)
    
    # 3. 检查评估任务
    logger.info("")
    logger.info("Step 3: Checking assessment tasks...")
    test_kafka_consumer(kafka_bootstrap, "assessment-tasks", timeout=10)
    
    # 4. 等待 LLM 处理
    logger.info("")
    logger.info("Step 4: Waiting for LLM processing (30s)...")
    time.sleep(30)
    
    # 5. 检查评估结果
    logger.info("")
    logger.info("Step 5: Checking assessment results...")
    test_kafka_consumer(kafka_bootstrap, "risk-assessment-results", timeout=15)
    
    logger.success("=== End-to-End Test Completed ===")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Test streaming pipeline')
    parser.add_argument(
        '--mode',
        choices=['producer', 'consumer', 'e2e'],
        default='e2e',
        help='Test mode'
    )
    parser.add_argument(
        '--topic',
        default='detection-results',
        help='Topic to consume (for consumer mode)'
    )
    parser.add_argument(
        '--kafka-bootstrap',
        default='localhost:9092',
        help='Kafka bootstrap servers'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Test duration in seconds'
    )
    parser.add_argument(
        '--num-messages',
        type=int,
        default=5,
        help='Number of messages to send (for producer mode)'
    )
    
    args = parser.parse_args()
    
    try:
        if args.mode == 'producer':
            test_kafka_producer(args.kafka_bootstrap, args.num_messages)
        elif args.mode == 'consumer':
            test_kafka_consumer(args.kafka_bootstrap, args.topic, args.duration)
        elif args.mode == 'e2e':
            test_end_to_end(args.kafka_bootstrap, args.duration)
    
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
