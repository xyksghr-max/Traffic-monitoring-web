"""Task scheduler service for distributed LLM API calls.

This service consumes assessment tasks from Kafka, dispatches them to LLM APIs
using the API key pool, and publishes results back to Kafka.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from kafka import KafkaConsumer, KafkaProducer
from loguru import logger
from openai import AsyncOpenAI, APIError, RateLimitError

from streaming.api_key_pool import APIKeyPool, APIKeyInfo
from streaming.kafka_config import (
    kafka_settings,
    ASSESSMENT_TASKS_TOPIC,
    RISK_ASSESSMENT_RESULTS_TOPIC,
    DLQ_TOPIC,
)
from streaming.kafka_messages import (
    AssessmentTaskMessage,
    RiskAssessmentResultMessage,
    AssessmentResult,
    LLMMetadata,
    TaskStatus,
)


class RateLimitException(Exception):
    """Exception raised when API rate limit is hit."""
    pass


class TaskScheduler:
    """Scheduler for LLM assessment tasks with API key pool management."""
    
    def __init__(
        self,
        api_key_pool: APIKeyPool,
        max_workers: int = 10,
        max_retries: int = 3,
        request_timeout: int = 30,
    ) -> None:
        """Initialize the task scheduler.
        
        Args:
            api_key_pool: Pool of API keys for LLM calls
            max_workers: Maximum concurrent workers
            max_retries: Maximum retry attempts per task
            request_timeout: Timeout for LLM API requests in seconds
        """
        self.api_key_pool = api_key_pool
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        
        # Kafka components
        self.consumer: Optional[KafkaConsumer] = None
        self.producer: Optional[KafkaProducer] = None
        
        # Task queue
        self.task_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        
        # Statistics
        self.stats = {
            "tasks_received": 0,
            "tasks_processed": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "tasks_retried": 0,
            "total_llm_latency": 0.0,
        }
        
        # Control flags
        self._running = False
        self._workers: list[asyncio.Task] = []
        
        logger.info(f"TaskScheduler initialized with {max_workers} workers")
    
    def _init_kafka(self) -> None:
        """Initialize Kafka consumer and producer."""
        consumer_config = kafka_settings.get_consumer_config(
            group_id="task-scheduler-group"
        )
        consumer_config["value_deserializer"] = lambda m: json.loads(m.decode("utf-8"))
        
        self.consumer = KafkaConsumer(
            ASSESSMENT_TASKS_TOPIC.name,
            **consumer_config
        )
        
        producer_config = kafka_settings.get_producer_config()
        producer_config["value_serializer"] = lambda v: json.dumps(v).encode("utf-8")
        
        self.producer = KafkaProducer(**producer_config)
        
        logger.info("Kafka consumer and producer initialized")
    
    async def start(self) -> None:
        """Start the task scheduler."""
        if self._running:
            logger.warning("TaskScheduler is already running")
            return
        
        self._running = True
        self._init_kafka()
        
        # Start consumer thread
        consumer_task = asyncio.create_task(self._consume_tasks())
        
        # Start worker pool
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(worker_id=i))
            self._workers.append(worker)
        
        logger.info(f"TaskScheduler started with {self.max_workers} workers")
        
        # Wait for tasks
        await asyncio.gather(consumer_task, *self._workers, return_exceptions=True)
    
    async def stop(self) -> None:
        """Stop the task scheduler."""
        self._running = False
        
        # Cancel all workers
        for worker in self._workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        
        # Close Kafka connections
        if self.consumer:
            self.consumer.close()
        if self.producer:
            self.producer.flush()
            self.producer.close()
        
        logger.info("TaskScheduler stopped")
    
    async def _consume_tasks(self) -> None:
        """Consume tasks from Kafka topic."""
        logger.info(f"Starting to consume from {ASSESSMENT_TASKS_TOPIC.name}")
        
        while self._running:
            try:
                # Poll messages (blocking with timeout)
                messages = self.consumer.poll(timeout_ms=1000)
                
                for topic_partition, records in messages.items():
                    for record in records:
                        try:
                            task = AssessmentTaskMessage.from_dict(record.value)
                            await self.task_queue.put(task)
                            self.stats["tasks_received"] += 1
                            
                            logger.debug(
                                f"Received task {task.task_id[:8]}... "
                                f"(camera_id={task.camera_id}, group_index={task.group_index})"
                            )
                        except Exception as e:
                            logger.error(f"Failed to deserialize task: {e}")
                            self._send_to_dlq(record.value, f"Deserialization error: {e}")
                
                # Manual commit after processing
                if not kafka_settings.kafka_consumer_enable_auto_commit:
                    self.consumer.commit()
                
            except Exception as e:
                logger.error(f"Error in consume loop: {e}")
                await asyncio.sleep(1)
    
    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine to process tasks.
        
        Args:
            worker_id: Unique identifier for this worker
        """
        logger.info(f"Worker-{worker_id} started")
        
        while self._running:
            try:
                # Get task from queue with timeout
                task = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )
                
                logger.debug(f"Worker-{worker_id} processing task {task.task_id[:8]}...")
                
                # Process the task
                result = await self._process_task(task)
                
                # Send result to Kafka
                self._publish_result(result)
                
                self.stats["tasks_processed"] += 1
                if result.status == TaskStatus.SUCCESS.value:
                    self.stats["tasks_succeeded"] += 1
                else:
                    self.stats["tasks_failed"] += 1
                
                self.task_queue.task_done()
                
            except asyncio.TimeoutError:
                # No task available, continue
                continue
            except Exception as e:
                logger.error(f"Worker-{worker_id} error: {e}")
                await asyncio.sleep(1)
        
        logger.info(f"Worker-{worker_id} stopped")
    
    async def _process_task(self, task: AssessmentTaskMessage) -> RiskAssessmentResultMessage:
        """Process a single assessment task.
        
        Args:
            task: The assessment task to process
            
        Returns:
            RiskAssessmentResultMessage with the result
        """
        retry_count = task.retry_count
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                # Acquire an API key from the pool
                api_key_info = await self.api_key_pool.acquire_key(timeout=10.0)
                
                if api_key_info is None:
                    logger.warning(f"No API key available for task {task.task_id[:8]}...")
                    await asyncio.sleep(1)
                    retry_count += 1
                    continue
                
                try:
                    # Call LLM API
                    assessment_result, llm_metadata = await self._call_llm_api(
                        task,
                        api_key_info
                    )
                    
                    # Mark key as successful
                    await self.api_key_pool.release_key(api_key_info, success=True)
                    
                    # Create success result
                    return RiskAssessmentResultMessage(
                        task_id=task.task_id,
                        origin_message_id=task.origin_message_id,
                        camera_id=task.camera_id,
                        group_index=task.group_index,
                        assessment_result=assessment_result,
                        llm_metadata=llm_metadata,
                        status=TaskStatus.SUCCESS.value,
                    )
                
                except RateLimitException as e:
                    # Rate limit error - mark key for cooling
                    await self.api_key_pool.release_key(
                        api_key_info,
                        success=False,
                        is_rate_limit=True
                    )
                    logger.warning(f"Rate limit hit for task {task.task_id[:8]}...: {e}")
                    last_error = str(e)
                    retry_count += 1
                    self.stats["tasks_retried"] += 1
                    await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                
                except Exception as e:
                    # Other API errors
                    await self.api_key_pool.release_key(api_key_info, success=False)
                    logger.error(f"LLM API error for task {task.task_id[:8]}...: {e}")
                    last_error = str(e)
                    retry_count += 1
                    self.stats["tasks_retried"] += 1
                    await asyncio.sleep(1)
            
            except Exception as e:
                logger.error(f"Unexpected error processing task {task.task_id[:8]}...: {e}")
                last_error = str(e)
                retry_count += 1
                await asyncio.sleep(1)
        
        # Max retries exceeded - create failure result
        return RiskAssessmentResultMessage(
            task_id=task.task_id,
            origin_message_id=task.origin_message_id,
            camera_id=task.camera_id,
            group_index=task.group_index,
            status=TaskStatus.FAILED.value,
            error_message=f"Max retries exceeded: {last_error}",
        )
    
    async def _call_llm_api(
        self,
        task: AssessmentTaskMessage,
        api_key_info: APIKeyInfo,
    ) -> tuple[AssessmentResult, LLMMetadata]:
        """Call the LLM API to perform risk assessment.
        
        Args:
            task: The assessment task
            api_key_info: API key information
            
        Returns:
            Tuple of (AssessmentResult, LLMMetadata)
            
        Raises:
            RateLimitException: If rate limit is hit
            APIError: For other API errors
        """
        start_time = time.time()
        
        # Build image data URL
        image_data_url = f"data:image/jpeg;base64,{task.group_image_base64}"
        
        # Build prompt
        prompt = self._build_prompt(task)
        
        # Initialize OpenAI client
        client = AsyncOpenAI(
            api_key=api_key_info.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=self.request_timeout,
        )
        
        try:
            # Call API
            response = await client.chat.completions.create(
                model=api_key_info.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional traffic safety analyst.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    },
                ],
            )
            
            latency_ms = (time.time() - start_time) * 1000
            self.stats["total_llm_latency"] += latency_ms
            
            # Extract response
            if not response.choices:
                raise APIError("Empty response from LLM")
            
            raw_text = response.choices[0].message.content
            
            # Parse JSON response
            assessment_result = self._parse_llm_response(raw_text)
            
            # Create metadata
            llm_metadata = LLMMetadata(
                model=api_key_info.model,
                api_key_id=api_key_info.key_id,
                latency_ms=latency_ms,
                raw_response=raw_text,
            )
            
            return assessment_result, llm_metadata
        
        except RateLimitError as e:
            raise RateLimitException(f"Rate limit exceeded: {e}")
        except APIError as e:
            logger.error(f"LLM API error: {e}")
            raise
    
    def _build_prompt(self, task: AssessmentTaskMessage) -> str:
        """Build the prompt for LLM assessment."""
        from algo.llm.prompts import DANGEROUS_DRIVING_PROMPT
        
        context = task.detection_context
        if not context:
            return DANGEROUS_DRIVING_PROMPT
        
        # Build object lines
        obj_lines = []
        for obj in context.detected_objects:
            obj_lines.append(
                f"- class={obj.class_name} confidence={obj.confidence:.2f} bbox={obj.bbox}"
            )
        
        # Build group summary
        group_info = context.group_metadata
        spatial = context.spatial_features
        
        summary_parts = [
            f"groupIndex={task.group_index}",
            f"count={group_info.get('object_count', 0)}",
            f"classes={group_info.get('classes', [])}",
        ]
        
        if spatial:
            if spatial.density:
                summary_parts.append(f"density={spatial.density:.2f}/1e4px")
            if spatial.avg_spacing:
                summary_parts.append(f"avgSpacing={spatial.avg_spacing:.1f}px")
            if spatial.min_spacing:
                summary_parts.append(f"minSpacing={spatial.min_spacing:.1f}px")
            if spatial.ped_vehicle_min_dist:
                summary_parts.append(f"pedVehicleMinDist={spatial.ped_vehicle_min_dist:.1f}px")
        
        group_summary = " ".join(summary_parts)
        
        return (
            f"{DANGEROUS_DRIVING_PROMPT}\n"
            f"[检测对象]\n{chr(10).join(obj_lines) or '无检测目标'}\n"
            f"[对象群组]\n- {group_summary}\n"
        )
    
    def _parse_llm_response(self, raw_text: str) -> AssessmentResult:
        """Parse LLM JSON response into AssessmentResult."""
        # Try to extract JSON from response
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try to find JSON in text
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(raw_text[start:end+1])
            else:
                raise ValueError("No valid JSON found in LLM response")
        
        # Extract first result if multiple
        results = data.get("results", [])
        if not results:
            return AssessmentResult(
                has_dangerous_driving=False,
                risk_level="none",
                risk_types=[],
                description="",
                confidence=0.0,
            )
        
        result = results[0]
        
        return AssessmentResult(
            has_dangerous_driving=data.get("hasDangerousDriving", False),
            risk_level=result.get("riskLevel", "none"),
            risk_types=result.get("riskTypes", []),
            description=result.get("description", ""),
            confidence=result.get("confidence", 0.0),
            danger_object_ids=result.get("triggerObjectIds", []),
            danger_object_count=result.get("dangerObjectCount", 0),
        )
    
    def _publish_result(self, result: RiskAssessmentResultMessage) -> None:
        """Publish result to Kafka topic."""
        try:
            self.producer.send(
                RISK_ASSESSMENT_RESULTS_TOPIC.name,
                value=result.to_dict(),
                key=str(result.camera_id).encode("utf-8"),
            )
            logger.debug(f"Published result for task {result.task_id[:8]}...")
        except Exception as e:
            logger.error(f"Failed to publish result: {e}")
            self._send_to_dlq(result.to_dict(), f"Publish error: {e}")
    
    def _send_to_dlq(self, message: Dict, error: str) -> None:
        """Send failed message to dead letter queue."""
        try:
            dlq_message = {
                "original_message": message,
                "error": error,
                "timestamp": time.time(),
            }
            self.producer.send(
                DLQ_TOPIC.name,
                value=dlq_message,
            )
            logger.warning(f"Sent message to DLQ: {error}")
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
    
    async def get_stats(self) -> Dict:
        """Get scheduler statistics."""
        pool_health = await self.api_key_pool.health_check()
        
        avg_latency = 0.0
        if self.stats["tasks_succeeded"] > 0:
            avg_latency = self.stats["total_llm_latency"] / self.stats["tasks_succeeded"]
        
        return {
            "scheduler": {
                "tasks_received": self.stats["tasks_received"],
                "tasks_processed": self.stats["tasks_processed"],
                "tasks_succeeded": self.stats["tasks_succeeded"],
                "tasks_failed": self.stats["tasks_failed"],
                "tasks_retried": self.stats["tasks_retried"],
                "average_llm_latency_ms": avg_latency,
                "queue_size": self.task_queue.qsize(),
                "max_workers": self.max_workers,
            },
            "api_key_pool": pool_health,
        }
