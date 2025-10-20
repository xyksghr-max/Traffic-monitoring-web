#!/usr/bin/env python3
"""启动 LLM 任务调度器"""

import sys
import yaml
import signal
from pathlib import Path

from loguru import logger

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from algo.scheduler import APIKeyPool, LLMTaskScheduler


def load_config():
    """加载配置"""
    # 加载 API Keys 配置
    api_keys_path = ROOT_DIR / "config" / "api_keys.yaml"
    with open(api_keys_path, 'r', encoding='utf-8') as f:
        api_config = yaml.safe_load(f)
    
    # 加载 Kafka 配置
    kafka_path = ROOT_DIR / "config" / "kafka.yaml"
    with open(kafka_path, 'r', encoding='utf-8') as f:
        kafka_config = yaml.safe_load(f)
    
    return api_config, kafka_config


def main():
    """主函数"""
    logger.info("=== Starting LLM Task Scheduler ===")
    
    try:
        # 加载配置
        api_config, kafka_config = load_config()
        
        # 初始化 API Key 池
        scheduler_config = api_config.get('scheduler', {})
        key_pool = APIKeyPool(
            keys=api_config['api_keys'],
            cooldown_seconds=scheduler_config.get('key_cooldown_seconds', 60),
            adaptive_cooldown=scheduler_config.get('adaptive_cooldown', {}).get('enabled', True),
            min_cooldown=scheduler_config.get('adaptive_cooldown', {}).get('min_cooldown', 10),
            max_cooldown=scheduler_config.get('adaptive_cooldown', {}).get('max_cooldown', 120),
        )
        
        # 初始化调度器
        kafka_bootstrap = kafka_config['kafka']['bootstrap_servers']
        scheduler = LLMTaskScheduler(
            key_pool=key_pool,
            kafka_bootstrap=kafka_bootstrap,
            input_topic=kafka_config['kafka']['topics']['assessment_tasks']['name'],
            output_topic=kafka_config['kafka']['topics']['risk_assessment_results']['name'],
            max_concurrent_tasks=scheduler_config.get('max_concurrent_tasks', 50),
        )
        
        # 启动调度器
        scheduler.start()
        
        # 设置信号处理
        def signal_handler(sig, frame):
            logger.info("Received shutdown signal")
            scheduler.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.success("=== LLM Task Scheduler started successfully ===")
        logger.info("Press Ctrl+C to stop")
        
        # 保持运行
        signal.pause()
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
