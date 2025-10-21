#!/usr/bin/env python3
"""
调试脚本：跟踪大模型数据流
用于诊断前端无法收到大模型返回结果的问题

功能：
1. 监听 Kafka 所有相关 Topic
2. 检查 Redis 中的数据
3. 输出完整的数据流路径
4. 高亮显示问题节点
"""

import redis
import json
import time
import sys
from pathlib import Path
from datetime import datetime
from confluent_kafka import Consumer, KafkaError
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from collections import deque

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

console = Console()


class LLMFlowDebugger:
    """大模型数据流调试器"""
    
    def __init__(
        self,
        kafka_bootstrap: str = "localhost:9092",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        max_history: int = 50
    ):
        """初始化调试器"""
        self.kafka_bootstrap = kafka_bootstrap
        self.redis_host = redis_host
        self.redis_port = redis_port
        
        # 数据历史记录
        self.detection_history = deque(maxlen=max_history)
        self.task_history = deque(maxlen=max_history)
        self.result_history = deque(maxlen=max_history)
        
        # 统计数据
        self.stats = {
            'detections_received': 0,
            'tasks_generated': 0,
            'llm_results_received': 0,
            'redis_stored': 0,
            'redis_not_found': 0,
            'websocket_published': 0,
        }
        
        # 初始化 Redis
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis_client.ping()
            console.print("[green]✅ Redis connected[/green]")
        except Exception as e:
            console.print(f"[red]❌ Redis connection failed: {e}[/red]")
            self.redis_client = None
        
        # 初始化 Kafka Consumer
        try:
            self.consumer = Consumer({
                'bootstrap.servers': kafka_bootstrap,
                'group.id': 'llm-flow-debugger',
                'auto.offset.reset': 'latest',
                'enable.auto.commit': True,
            })
            self.consumer.subscribe([
                'detection-results',
                'assessment-tasks',
                'risk-assessment-results'
            ])
            console.print("[green]✅ Kafka consumer initialized[/green]")
        except Exception as e:
            console.print(f"[red]❌ Kafka consumer failed: {e}[/red]")
            self.consumer = None
    
    def check_redis_key(self, key: str) -> bool:
        """检查 Redis 中的 key 是否存在"""
        if not self.redis_client:
            return False
        try:
            return self.redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check Redis key {key}: {e}")
            return False
    
    def get_redis_value(self, key: str) -> dict | None:
        """获取 Redis 中的值"""
        if not self.redis_client:
            return None
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Failed to get Redis value for {key}: {e}")
            return None
    
    def handle_detection_result(self, msg_value: dict):
        """处理检测结果消息"""
        message_id = msg_value.get('messageId')
        camera_id = msg_value.get('cameraId')
        groups = msg_value.get('trafficGroups', [])
        
        self.stats['detections_received'] += 1
        
        # 检查 Redis 存储
        redis_stored = False
        if message_id:
            redis_key = f"detection:{message_id}"
            redis_stored = self.check_redis_key(redis_key)
            if redis_stored:
                self.stats['redis_stored'] += 1
            else:
                self.stats['redis_not_found'] += 1
        
        record = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'messageId': message_id,
            'cameraId': camera_id,
            'groups': len(groups),
            'redis_stored': '✅' if redis_stored else '❌',
        }
        self.detection_history.append(record)
        
        console.print(
            f"[cyan]📥 Detection:[/cyan] messageId={message_id}, "
            f"camera={camera_id}, groups={len(groups)}, "
            f"redis={record['redis_stored']}"
        )
    
    def handle_assessment_task(self, msg_value: dict):
        """处理评估任务消息"""
        task_id = msg_value.get('taskId')
        request_id = msg_value.get('requestId')
        camera_id = msg_value.get('cameraId')
        group_index = msg_value.get('groupIndex')
        
        self.stats['tasks_generated'] += 1
        
        # 检查 Redis 中是否有对应的检测数据
        redis_exists = False
        if request_id:
            redis_key = f"detection:{request_id}"
            redis_exists = self.check_redis_key(redis_key)
        
        record = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'taskId': task_id,
            'requestId': request_id,
            'cameraId': camera_id,
            'groupIndex': group_index,
            'redis_exists': '✅' if redis_exists else '❌',
        }
        self.task_history.append(record)
        
        console.print(
            f"[yellow]📋 Task:[/yellow] taskId={task_id}, "
            f"requestId={request_id}, camera={camera_id}, "
            f"group={group_index}, redis={record['redis_exists']}"
        )
    
    def handle_llm_result(self, msg_value: dict):
        """处理 LLM 评估结果消息"""
        request_id = msg_value.get('requestId')
        camera_id = msg_value.get('cameraId')
        risk_level = msg_value.get('maxRiskLevel', 'none')
        has_dangerous = msg_value.get('hasDangerousDriving', False)
        results = msg_value.get('results', [])
        
        self.stats['llm_results_received'] += 1
        
        # 检查 Redis 中是否有对应的检测数据
        redis_detection_exists = False
        if request_id:
            redis_key = f"detection:{request_id}"
            redis_detection_exists = self.check_redis_key(redis_key)
            if not redis_detection_exists:
                console.print(
                    f"[red]⚠️  WARNING: Detection data not found in Redis for {request_id}[/red]"
                )
        
        # 检查 WebSocket 发布
        # (这个需要监听 Redis pubsub，这里简化处理)
        
        record = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'requestId': request_id,
            'cameraId': camera_id,
            'riskLevel': risk_level,
            'hasDangerous': has_dangerous,
            'resultCount': len(results),
            'redis_exists': '✅' if redis_detection_exists else '❌',
        }
        self.result_history.append(record)
        
        # 打印完整的 LLM 结果（调试用）
        console.print(
            Panel(
                json.dumps(msg_value, indent=2, ensure_ascii=False),
                title=f"🤖 LLM Result (requestId={request_id})",
                border_style="green" if has_dangerous else "blue"
            )
        )
    
    def display_stats(self):
        """显示统计信息"""
        table = Table(title="📊 Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")
        
        table.add_row("Detections Received", str(self.stats['detections_received']))
        table.add_row("Tasks Generated", str(self.stats['tasks_generated']))
        table.add_row("LLM Results Received", str(self.stats['llm_results_received']))
        table.add_row("Redis Stored", str(self.stats['redis_stored']))
        table.add_row("Redis Not Found", str(self.stats['redis_not_found']))
        
        return table
    
    def display_recent_detections(self):
        """显示最近的检测记录"""
        table = Table(title="📥 Recent Detections")
        table.add_column("Time", style="dim")
        table.add_column("MessageID", style="cyan")
        table.add_column("Camera", justify="right")
        table.add_column("Groups", justify="right")
        table.add_column("Redis", justify="center")
        
        for record in list(self.detection_history)[-10:]:
            table.add_row(
                record['timestamp'],
                record['messageId'][:8] if record['messageId'] else 'N/A',
                str(record['cameraId']),
                str(record['groups']),
                record['redis_stored']
            )
        
        return table
    
    def display_recent_tasks(self):
        """显示最近的任务记录"""
        table = Table(title="📋 Recent Tasks")
        table.add_column("Time", style="dim")
        table.add_column("TaskID", style="yellow")
        table.add_column("RequestID", style="cyan")
        table.add_column("Camera", justify="right")
        table.add_column("Group", justify="right")
        table.add_column("Redis", justify="center")
        
        for record in list(self.task_history)[-10:]:
            table.add_row(
                record['timestamp'],
                record['taskId'][:12] if record['taskId'] else 'N/A',
                record['requestId'][:8] if record['requestId'] else 'N/A',
                str(record['cameraId']),
                str(record['groupIndex']),
                record['redis_exists']
            )
        
        return table
    
    def display_recent_results(self):
        """显示最近的 LLM 结果"""
        table = Table(title="🤖 Recent LLM Results")
        table.add_column("Time", style="dim")
        table.add_column("RequestID", style="cyan")
        table.add_column("Camera", justify="right")
        table.add_column("Risk", style="bold")
        table.add_column("Dangerous", justify="center")
        table.add_column("Results", justify="right")
        table.add_column("Redis", justify="center")
        
        for record in list(self.result_history)[-10:]:
            risk_style = {
                'high': 'red',
                'medium': 'yellow',
                'low': 'blue',
                'none': 'dim'
            }.get(record['riskLevel'], 'white')
            
            table.add_row(
                record['timestamp'],
                record['requestId'][:8] if record['requestId'] else 'N/A',
                str(record['cameraId']),
                f"[{risk_style}]{record['riskLevel']}[/{risk_style}]",
                '✅' if record['hasDangerous'] else '❌',
                str(record['resultCount']),
                record['redis_exists']
            )
        
        return table
    
    def run(self):
        """运行调试器"""
        console.print(
            Panel(
                "[bold cyan]LLM Flow Debugger[/bold cyan]\n"
                "Monitoring Kafka topics and Redis data flow...\n"
                "Press Ctrl+C to exit",
                border_style="cyan"
            )
        )
        
        if not self.consumer:
            console.print("[red]Cannot run without Kafka consumer[/red]")
            return
        
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Kafka error: {msg.error()}")
                        continue
                
                topic = msg.topic()
                
                try:
                    msg_value = json.loads(msg.value().decode('utf-8'))
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                    continue
                
                # 根据 topic 处理消息
                if topic == 'detection-results':
                    self.handle_detection_result(msg_value)
                elif topic == 'assessment-tasks':
                    self.handle_assessment_task(msg_value)
                elif topic == 'risk-assessment-results':
                    self.handle_llm_result(msg_value)
                
                # 每 5 秒显示一次统计
                if int(time.time()) % 5 == 0:
                    console.clear()
                    console.print(self.display_stats())
                    console.print(self.display_recent_detections())
                    console.print(self.display_recent_tasks())
                    console.print(self.display_recent_results())
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping debugger...[/yellow]")
        finally:
            if self.consumer:
                self.consumer.close()
            console.print("[green]Debugger stopped[/green]")


if __name__ == "__main__":
    debugger = LLMFlowDebugger()
    debugger.run()
