"""LLM Task Scheduler with API Key pooling and concurrent execution."""

from __future__ import annotations

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
import sys

from loguru import logger

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from algo.scheduler.api_key_pool import APIKeyPool, APIKey
from algo.kafka.base_consumer import BaseKafkaConsumer
from algo.kafka.detection_producer import DetectionResultProducer
from algo.llm.prompts import DANGEROUS_DRIVING_PROMPT


class LLMTaskScheduler:
    """
    LLM 任务调度器
    
    功能：
    1. 从 Kafka 消费评估任务
    2. 使用 API Key 池并发调用大模型
    3. 将评估结果发送到 Kafka
    """
    
    def __init__(
        self,
        key_pool: APIKeyPool,
        kafka_bootstrap: str,
        input_topic: str = "assessment-tasks",
        output_topic: str = "risk-assessment-results",
        max_concurrent_tasks: int = 50,
        llm_model: str = "qwen-vl-plus",
        llm_timeout: int = 30,
        max_retries: int = 2
    ):
        """
        初始化调度器
        
        Args:
            key_pool: API Key 池
            kafka_bootstrap: Kafka 服务器地址
            input_topic: 输入 Topic (评估任务)
            output_topic: 输出 Topic (评估结果)
            max_concurrent_tasks: 最大并发任务数
            llm_model: LLM 模型名称
            llm_timeout: LLM 请求超时时间
            max_retries: 最大重试次数
        """
        self.key_pool = key_pool
        self.max_concurrent_tasks = max_concurrent_tasks
        self.llm_model = llm_model
        self.llm_timeout = llm_timeout
        self.max_retries = max_retries
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
        # 信号量控制并发数
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        
        # Kafka 消费者
        self.task_consumer = BaseKafkaConsumer(
            bootstrap_servers=kafka_bootstrap,
            group_id="llm-task-scheduler",
            topics=[input_topic],
            message_handler=self._handle_task_sync
        )
        
        # Kafka 生产者
        self.result_producer = DetectionResultProducer(
            bootstrap_servers=kafka_bootstrap,
            topic=output_topic
        )
        
        self.running = False
        self.pending_tasks = asyncio.Queue()
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        
        logger.info(f"LLM Task Scheduler initialized (max_concurrent={max_concurrent_tasks})")
    
    def _handle_task_sync(self, task_data: Dict[str, Any]):
        """同步处理任务（从 Kafka Consumer 调用）"""
        if self.event_loop and self.running:
            asyncio.run_coroutine_threadsafe(
                self.pending_tasks.put(task_data),
                self.event_loop
            )
    
    async def call_llm_api(
        self,
        api_key: APIKey,
        task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用指定的 API Key 调用大模型 API
        
        Args:
            api_key: API Key
            task: 评估任务
            
        Returns:
            评估结果
        """
        headers = {
            "Authorization": f"Bearer {api_key.key}",
            "Content-Type": "application/json"
        }
        
        # 构造请求payload
        group_image = task.get('groupImageBase64', '')
        prompt = self._build_prompt(task)
        
        payload = {
            "model": self.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional traffic safety analyst."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": group_image}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        }
        
        for attempt in range(self.max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.llm_timeout)
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            return self._parse_llm_response(result, task)
                        elif response.status == 429:  # Rate limit
                            logger.warning(
                                f"Rate limit hit for {api_key.key_id}, "
                                f"attempt {attempt + 1}/{self.max_retries + 1}"
                            )
                            await asyncio.sleep(2 ** attempt)  # 指数退避
                        else:
                            error_text = await response.text()
                            logger.error(f"LLM API error {response.status}: {error_text[:200]}")
                            if attempt == self.max_retries:
                                raise Exception(f"API call failed: HTTP {response.status}")
            
            except asyncio.TimeoutError:
                logger.error(f"LLM API timeout for {api_key.key_id}, attempt {attempt + 1}")
                if attempt == self.max_retries:
                    raise
            except Exception as e:
                logger.error(f"LLM API exception: {e}")
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(1)
        
        return self._empty_result(task)
    
    async def process_task(self, task: Dict[str, Any]):
        """处理单个评估任务"""
        task_id = task.get('taskId', 'unknown')
        
        async with self.semaphore:  # 限制并发数
            api_key = None
            start_time = time.time()
            
            try:
                # 获取 API Key
                api_key = self.key_pool.acquire_key(timeout=10.0)
                if not api_key:
                    logger.error(f"Failed to acquire API key for task {task_id}")
                    error_result = self._error_result(task, "No available API key")
                    self._send_result(error_result, task.get('cameraId', 0))
                    return
                
                # 调用 LLM API
                result = await self.call_llm_api(api_key, task)
                
                # 释放 Key (成功)
                self.key_pool.release_key(api_key, success=True)
                
                # 添加元数据
                result['metadata'] = {
                    'llmLatency': time.time() - start_time,
                    'llmModel': self.llm_model,
                    'apiKeyId': api_key.key_id,
                    'retryCount': 0,
                }
                
                # 发送结果
                self._send_result(result, task.get('cameraId', 0))
                logger.info(f"Task {task_id} completed successfully in {time.time() - start_time:.2f}s")
                
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                
                # 释放 Key (失败)
                if api_key:
                    self.key_pool.release_key(api_key, success=False)
                
                # 发送错误结果
                error_result = self._error_result(task, str(e))
                self._send_result(error_result, task.get('cameraId', 0))
    
    def _send_result(self, result: Dict[str, Any], camera_id: int):
        """发送结果到 Kafka"""
        try:
            self.result_producer.send(result, camera_id)
        except Exception as e:
            logger.error(f"Failed to send result to Kafka: {e}")
    
    async def worker_loop(self):
        """工作线程：持续处理任务"""
        logger.info("Worker loop started")
        
        while self.running:
            try:
                task = await asyncio.wait_for(self.pending_tasks.get(), timeout=1.0)
                asyncio.create_task(self.process_task(task))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
    
    def start(self):
        """启动调度器"""
        import threading
        
        self.running = True
        
        # 启动 Kafka 消费线程
        consumer_thread = threading.Thread(target=self.task_consumer.start, daemon=True)
        consumer_thread.start()
        logger.info("Kafka consumer thread started")
        
        # 启动异步事件循环
        def run_event_loop():
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_until_complete(self.worker_loop())
        
        loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        loop_thread.start()
        logger.info("Async worker loop started")
        
        logger.success("LLM Task Scheduler started successfully")
    
    def stop(self):
        """停止调度器"""
        logger.info("Stopping LLM Task Scheduler...")
        self.running = False
        self.task_consumer.stop()
        self.result_producer.close()
        logger.info("LLM Task Scheduler stopped")
    
    def _build_prompt(self, task: Dict[str, Any]) -> str:
        """构建 LLM 提示词"""
        objects = task.get('detectedObjects', [])
        metadata = task.get('groupMetadata', {})
        
        obj_lines = []
        for obj in objects:
            bbox = obj.get('bbox', [])
            obj_lines.append(
                f"- class={obj.get('class')} confidence={obj.get('confidence', 0):.2f} bbox={bbox}"
            )
        
        objects_summary = '\n'.join(obj_lines) or 'No objects'
        
        prompt = f"""{DANGEROUS_DRIVING_PROMPT}

[Group Information]
Object count: {metadata.get('objectCount', 0)}
Object classes: {', '.join(metadata.get('classes', []))}

[Detected Objects in Group]
{objects_summary}

Please analyze this traffic scene and return results in JSON format with fields:
- riskLevel: "none" | "low" | "medium" | "high"
- confidence: 0.0-1.0
- riskTypes: array of risk types
- description: detailed description
- dangerObjectCount: number of dangerous objects
- triggerObjectIds: array of object IDs that triggered the risk
"""
        return prompt
    
    def _parse_llm_response(self, response: dict, task: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 响应"""
        choices = response.get('choices', [])
        if not choices:
            return self._empty_result(task)
        
        content = choices[0].get('message', {}).get('content', '')
        
        # 尝试解析 JSON
        try:
            # 提取 JSON 部分
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                json_str = content[start:end + 1]
                parsed = json.loads(json_str)
            else:
                parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {content[:200]}")
            parsed = {
                'riskLevel': 'none',
                'confidence': 0.0,
                'riskTypes': [],
                'description': content[:200] if content else 'No response'
            }
        
        return {
            'messageId': f"{task.get('taskId', 'unknown')}_result",
            'requestId': task.get('requestId'),
            'cameraId': task.get('cameraId'),
            'timestamp': task.get('timestamp'),
            'results': [
                {
                    'groupIndex': task.get('groupIndex'),
                    'riskLevel': parsed.get('riskLevel', 'none'),
                    'confidence': float(parsed.get('confidence', 0.0)),
                    'riskTypes': parsed.get('riskTypes', []),
                    'description': parsed.get('description', ''),
                    'dangerObjectCount': parsed.get('dangerObjectCount'),
                    'triggerObjectIds': parsed.get('triggerObjectIds', []),
                }
            ],
            'hasDangerousDriving': parsed.get('riskLevel', 'none') != 'none',
            'maxRiskLevel': parsed.get('riskLevel', 'none'),
        }
    
    def _empty_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """空结果"""
        return {
            'messageId': f"{task.get('taskId', 'unknown')}_result",
            'requestId': task.get('requestId'),
            'cameraId': task.get('cameraId'),
            'timestamp': task.get('timestamp'),
            'results': [],
            'hasDangerousDriving': False,
            'maxRiskLevel': 'none',
        }
    
    def _error_result(self, task: Dict[str, Any], error: str) -> Dict[str, Any]:
        """错误结果"""
        result = self._empty_result(task)
        result['error'] = error
        result['metadata'] = {
            'llmLatency': 0.0,
            'llmModel': self.llm_model,
            'apiKeyId': None,
            'retryCount': self.max_retries,
        }
        return result
