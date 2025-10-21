"""Simple task generator (Python version, no Flink required)."""

from __future__ import annotations

import threading
from typing import Dict, Any
from pathlib import Path
import sys

from loguru import logger

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from algo.kafka.base_consumer import BaseKafkaConsumer
from algo.kafka.detection_producer import DetectionResultProducer


class SimpleTaskGenerator:
    """
    简化版任务生成器 (不使用 Flink)
    
    功能：
    1. 消费检测结果 Topic
    2. 为每个群组生成评估任务
    3. 发送到任务队列 Topic
    """
    
    def __init__(self, kafka_bootstrap: str):
        """
        初始化任务生成器
        
        Args:
            kafka_bootstrap: Kafka 服务器地址
        """
        self.consumer = BaseKafkaConsumer(
            bootstrap_servers=kafka_bootstrap,
            group_id="simple-task-generator",
            topics=["detection-results"],
            message_handler=self.handle_detection_result
        )
        
        self.task_producer = DetectionResultProducer(
            bootstrap_servers=kafka_bootstrap,
            topic="assessment-tasks"
        )
        
        logger.info("Simple Task Generator initialized")
    
    def handle_detection_result(self, data: Dict[str, Any]):
        """
        处理检测结果并生成评估任务
        
        Args:
            data: 检测结果数据
        """
        try:
            message_id = data.get('messageId')
            camera_id = data.get('cameraId')
            
            logger.info(
                "📥 Received detection result: messageId={}, cameraId={}",
                message_id,
                camera_id
            )
            
            if camera_id is None:
                logger.warning("Detection result missing cameraId, skipping")
                return
                
            timestamp = data.get('timestamp')
            detected_objects = data.get('detectedObjects', [])
            traffic_groups = data.get('trafficGroups', [])
            group_images = data.get('groupImages', [])
            
            # 为每个群组生成任务
            task_count = 0
            for group_image in group_images:
                group_index = group_image.get('groupIndex')
                if group_index is None:
                    continue
                
                # 找到对应的群组元数据
                group_metadata = None
                for group in traffic_groups:
                    if group.get('groupIndex') == group_index:
                        group_metadata = group
                        break
                
                # 过滤该群组的检测对象
                member_indices = group_metadata.get('memberIndices', []) if group_metadata else []
                group_objects = []
                if member_indices:
                    group_objects = [
                        detected_objects[i] for i in member_indices
                        if 0 <= i < len(detected_objects)
                    ]
                else:
                    # 如果没有 memberIndices，使用所有对象
                    group_objects = detected_objects
                
                # 构建任务
                task = {
                    'taskId': f"{message_id}_group{group_index}",
                    'requestId': message_id,
                    'cameraId': camera_id,
                    'timestamp': timestamp,
                    'groupIndex': group_index,
                    'groupImageBase64': group_image.get('imageBase64', ''),
                    'groupImageUrl': group_image.get('imageUrl', ''),
                    'detectedObjects': group_objects,
                    'groupMetadata': {
                        'objectCount': group_metadata.get('objectCount', 0) if group_metadata else 0,
                        'classes': group_metadata.get('classes', []) if group_metadata else [],
                        'bbox': group_metadata.get('bbox', []) if group_metadata else [],
                    }
                }
                
                # 发送任务
                self.task_producer.send(task, camera_id)
                task_count += 1
            
            if task_count > 0:
                logger.info(
                    "📤 Generated {} assessment tasks for camera {} (messageId={})",
                    task_count,
                    camera_id,
                    message_id
                )
            else:
                logger.debug(f"No tasks generated for camera {camera_id} (no groups)")
                
        except Exception as e:
            logger.error(f"Failed to generate tasks: {e}", exc_info=True)
    
    def start(self):
        """启动任务生成器"""
        logger.info("Starting Simple Task Generator...")
        thread = threading.Thread(target=self.consumer.start, daemon=True)
        thread.start()
        logger.success("Simple Task Generator started")
        return thread
    
    def stop(self):
        """停止任务生成器"""
        logger.info("Stopping Simple Task Generator...")
        self.consumer.stop()
        self.task_producer.close()
        logger.info("Simple Task Generator stopped")
