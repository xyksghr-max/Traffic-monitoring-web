"""Prometheus metrics exporter for streaming system."""

from __future__ import annotations

from typing import Optional
from prometheus_client import Counter, Histogram, Gauge, Info
from loguru import logger

# ========================================
# Detection Metrics
# ========================================

detection_total = Counter(
    'detection_total',
    'Total number of detection frames processed',
    ['camera_id', 'model_type']
)

detection_latency = Histogram(
    'detection_latency_seconds',
    'Detection processing latency in seconds',
    ['camera_id', 'model_type'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
)

detected_objects_total = Counter(
    'detected_objects_total',
    'Total number of objects detected',
    ['camera_id', 'class_name']
)

traffic_groups_total = Counter(
    'traffic_groups_total',
    'Total number of traffic groups formed',
    ['camera_id']
)

# ========================================
# Kafka Metrics
# ========================================

kafka_messages_sent = Counter(
    'kafka_messages_sent_total',
    'Total number of Kafka messages sent',
    ['topic', 'camera_id']
)

kafka_messages_received = Counter(
    'kafka_messages_received_total',
    'Total number of Kafka messages received',
    ['topic', 'consumer_group']
)

kafka_send_errors = Counter(
    'kafka_send_errors_total',
    'Total number of Kafka send errors',
    ['topic', 'error_type']
)

kafka_lag = Gauge(
    'kafka_consumer_lag',
    'Current Kafka consumer lag',
    ['topic', 'partition', 'consumer_group']
)

# ========================================
# LLM API Metrics
# ========================================

llm_requests_total = Counter(
    'llm_requests_total',
    'Total number of LLM API requests',
    ['model', 'api_key_id', 'status']
)

llm_latency = Histogram(
    'llm_latency_seconds',
    'LLM API request latency in seconds',
    ['model', 'api_key_id'],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

llm_token_usage = Counter(
    'llm_token_usage_total',
    'Total number of tokens used by LLM',
    ['model', 'token_type']  # token_type: prompt_tokens, completion_tokens
)

llm_concurrent_tasks = Gauge(
    'llm_concurrent_tasks',
    'Current number of concurrent LLM tasks',
    ['scheduler_id']
)

# ========================================
# API Key Pool Metrics
# ========================================

api_key_pool_size = Gauge(
    'api_key_pool_size',
    'Total number of API keys in pool',
    ['pool_id']
)

api_key_status = Gauge(
    'api_key_status',
    'API key status (1=available, 2=in_use, 3=cooling, 4=disabled)',
    ['pool_id', 'key_id', 'status']
)

api_key_success_rate = Gauge(
    'api_key_success_rate',
    'Success rate of API key (0.0-1.0)',
    ['pool_id', 'key_id']
)

api_key_total_calls = Counter(
    'api_key_total_calls',
    'Total number of calls made with API key',
    ['pool_id', 'key_id']
)

api_key_cooldown_seconds = Gauge(
    'api_key_cooldown_seconds',
    'Current cooldown time for API key',
    ['pool_id', 'key_id']
)

# ========================================
# Task Metrics
# ========================================

tasks_generated = Counter(
    'tasks_generated_total',
    'Total number of assessment tasks generated',
    ['camera_id']
)

tasks_processed = Counter(
    'tasks_processed_total',
    'Total number of tasks processed',
    ['status']  # status: success, failure, retry
)

task_queue_size = Gauge(
    'task_queue_size',
    'Current number of tasks in queue',
    ['queue_type']  # queue_type: pending, processing
)

# ========================================
# Risk Assessment Metrics
# ========================================

risk_alerts_total = Counter(
    'risk_alerts_total',
    'Total number of risk alerts generated',
    ['camera_id', 'risk_level']  # risk_level: high, medium, low
)

risk_types_detected = Counter(
    'risk_types_detected_total',
    'Total number of risk types detected',
    ['risk_type']  # risk_type: lane_violation, unsafe_distance, etc.
)

# ========================================
# System Metrics
# ========================================

active_cameras = Gauge(
    'active_cameras',
    'Current number of active camera streams'
)

pipeline_errors = Counter(
    'pipeline_errors_total',
    'Total number of pipeline errors',
    ['error_type', 'component']
)

system_info = Info(
    'system_info',
    'System information'
)

# ========================================
# Helper Functions
# ========================================

def record_detection(camera_id: str, model_type: str, latency: float, num_objects: int, num_groups: int):
    """Record detection metrics."""
    detection_total.labels(camera_id=camera_id, model_type=model_type).inc()
    detection_latency.labels(camera_id=camera_id, model_type=model_type).observe(latency)
    traffic_groups_total.labels(camera_id=camera_id).inc(num_groups)


def record_kafka_send(topic: str, camera_id: str, success: bool = True, error_type: Optional[str] = None):
    """Record Kafka send metrics."""
    if success:
        kafka_messages_sent.labels(topic=topic, camera_id=camera_id).inc()
    else:
        kafka_send_errors.labels(topic=topic, error_type=error_type or 'unknown').inc()


def record_llm_request(model: str, api_key_id: str, latency: float, status: str, 
                       prompt_tokens: int = 0, completion_tokens: int = 0):
    """Record LLM API metrics."""
    llm_requests_total.labels(model=model, api_key_id=api_key_id, status=status).inc()
    if status == 'success':
        llm_latency.labels(model=model, api_key_id=api_key_id).observe(latency)
        if prompt_tokens > 0:
            llm_token_usage.labels(model=model, token_type='prompt_tokens').inc(prompt_tokens)
        if completion_tokens > 0:
            llm_token_usage.labels(model=model, token_type='completion_tokens').inc(completion_tokens)


def update_api_key_pool_metrics(pool_id: str, keys_status: dict):
    """Update API key pool metrics.
    
    Args:
        pool_id: Identifier for the API key pool
        keys_status: Dict mapping key_id to status dict with:
            - status: str (AVAILABLE, IN_USE, COOLING, DISABLED)
            - success_rate: float
            - total_calls: int
            - cooldown_until: Optional[float]
    """
    api_key_pool_size.labels(pool_id=pool_id).set(len(keys_status))
    
    status_map = {
        'AVAILABLE': 1,
        'IN_USE': 2,
        'COOLING': 3,
        'DISABLED': 4,
    }
    
    for key_id, info in keys_status.items():
        status_code = status_map.get(info.get('status', 'AVAILABLE'), 1)
        api_key_status.labels(pool_id=pool_id, key_id=key_id, status=info.get('status', 'AVAILABLE')).set(status_code)
        api_key_success_rate.labels(pool_id=pool_id, key_id=key_id).set(info.get('success_rate', 0.0))
        
        total_calls = info.get('total_calls', 0)
        # Counter only increases, so we need to track previous value
        # For simplicity, we'll use inc() with the difference
        # In production, consider using a Gauge or storing state
        api_key_total_calls.labels(pool_id=pool_id, key_id=key_id).inc(0)  # Just to register the label
        
        cooldown_until = info.get('cooldown_until')
        if cooldown_until:
            import time
            remaining = max(0, cooldown_until - time.time())
            api_key_cooldown_seconds.labels(pool_id=pool_id, key_id=key_id).set(remaining)
        else:
            api_key_cooldown_seconds.labels(pool_id=pool_id, key_id=key_id).set(0)


def record_risk_alert(camera_id: str, risk_level: str, risk_types: list[str]):
    """Record risk alert metrics."""
    risk_alerts_total.labels(camera_id=camera_id, risk_level=risk_level).inc()
    for risk_type in risk_types:
        risk_types_detected.labels(risk_type=risk_type).inc()


logger.info("Prometheus metrics initialized")
