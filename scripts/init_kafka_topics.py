#!/usr/bin/env python3
"""
初始化 Kafka Topics 脚本
创建系统所需的所有 Kafka Topics
"""

import sys
import yaml
from pathlib import Path
from confluent_kafka.admin import AdminClient, NewTopic
from loguru import logger

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def load_kafka_config():
    """加载 Kafka 配置"""
    config_path = ROOT_DIR / "config" / "kafka.yaml"
    
    if not config_path.exists():
        logger.error(f"Kafka 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config['kafka']


def create_topics(kafka_config):
    """创建 Kafka Topics"""
    bootstrap_servers = kafka_config['bootstrap_servers']
    topics_config = kafka_config['topics']
    
    # 创建 Admin 客户端
    admin_client = AdminClient({'bootstrap.servers': bootstrap_servers})
    
    # 准备要创建的 Topics
    new_topics = []
    
    for topic_key, topic_config in topics_config.items():
        topic_name = topic_config['name']
        partitions = topic_config.get('partitions', 16)
        replication_factor = topic_config.get('replication_factor', 1)
        retention_ms = topic_config.get('retention_ms', 3600000)
        
        new_topic = NewTopic(
            topic=topic_name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            config={
                'retention.ms': str(retention_ms),
                'compression.type': 'snappy',
                'cleanup.policy': 'delete',
                'max.message.bytes': '1048576',  # 1MB
            }
        )
        new_topics.append(new_topic)
        logger.info(f"准备创建 Topic: {topic_name} (分区={partitions}, 副本={replication_factor})")
    
    # 创建 Topics
    futures = admin_client.create_topics(new_topics)
    
    # 等待创建完成
    for topic_name, future in futures.items():
        try:
            future.result()  # 阻塞等待结果
            logger.success(f"✅ Topic 创建成功: {topic_name}")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.warning(f"⚠️  Topic 已存在: {topic_name}")
            else:
                logger.error(f"❌ Topic 创建失败: {topic_name}, 错误: {e}")


def verify_topics(kafka_config):
    """验证 Topics 是否创建成功"""
    bootstrap_servers = kafka_config['bootstrap_servers']
    admin_client = AdminClient({'bootstrap.servers': bootstrap_servers})
    
    # 获取集群中的所有 Topics
    metadata = admin_client.list_topics(timeout=10)
    existing_topics = set(metadata.topics.keys())
    
    logger.info("\n=== Kafka Topics 验证 ===")
    for topic_key, topic_config in kafka_config['topics'].items():
        topic_name = topic_config['name']
        if topic_name in existing_topics:
            topic_metadata = metadata.topics[topic_name]
            logger.info(f"✓ {topic_name}: {len(topic_metadata.partitions)} 个分区")
        else:
            logger.error(f"✗ {topic_name}: 不存在")


def main():
    logger.info("=== 开始初始化 Kafka Topics ===")
    
    # 加载配置
    kafka_config = load_kafka_config()
    
    # 创建 Topics
    create_topics(kafka_config)
    
    # 验证创建结果
    verify_topics(kafka_config)
    
    logger.success("\n=== Kafka Topics 初始化完成 ===")


if __name__ == "__main__":
    main()
