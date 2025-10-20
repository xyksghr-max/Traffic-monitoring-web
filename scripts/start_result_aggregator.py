#!/usr/bin/env python3
"""启动结果聚合器"""

import sys
import yaml
import signal
from pathlib import Path

from loguru import logger

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from algo.consumers import ResultAggregator


def load_config():
    """加载配置"""
    kafka_path = ROOT_DIR / "config" / "kafka.yaml"
    with open(kafka_path, 'r', encoding='utf-8') as f:
        kafka_config = yaml.safe_load(f)
    return kafka_config


def main():
    """主函数"""
    logger.info("=== Starting Result Aggregator ===")
    
    try:
        # 加载配置
        kafka_config = load_config()
        kafka_bootstrap = kafka_config['kafka']['bootstrap_servers']
        
        # 初始化聚合器
        aggregator = ResultAggregator(
            kafka_bootstrap=kafka_bootstrap,
            redis_host='localhost',
            redis_port=6379,
            redis_db=0,
            enable_redis=True
        )
        
        # 启动聚合器
        thread = aggregator.start()
        
        # 设置信号处理
        def signal_handler(sig, frame):
            logger.info("Received shutdown signal")
            aggregator.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.success("=== Result Aggregator started successfully ===")
        logger.info("Press Ctrl+C to stop")
        
        # 等待线程
        thread.join()
        
    except Exception as e:
        logger.error(f"Failed to start result aggregator: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
