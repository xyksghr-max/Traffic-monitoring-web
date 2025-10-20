"""Streaming module for distributed traffic monitoring system.

This module provides Kafka integration, API key pool management,
and task scheduling for high-concurrency LLM API calls.
"""

from streaming.kafka_messages import (
    DetectionResultMessage,
    AssessmentTaskMessage,
    RiskAssessmentResultMessage,
    DetectedObject,
    TrafficGroup,
    SpatialFeatures,
    MessageType,
    TaskStatus,
    RiskLevel,
)

from streaming.kafka_config import (
    kafka_settings,
    KafkaSettings,
    TopicConfig,
    DETECTION_RESULTS_TOPIC,
    ASSESSMENT_TASKS_TOPIC,
    RISK_ASSESSMENT_RESULTS_TOPIC,
    DLQ_TOPIC,
)

from streaming.api_key_pool import (
    APIKeyPool,
    APIKeyInfo,
    KeyStatus,
    create_key_pool_from_config,
)

from streaming.task_scheduler import (
    TaskScheduler,
    RateLimitException,
)

__version__ = "2.0.0"
__all__ = [
    # Messages
    "DetectionResultMessage",
    "AssessmentTaskMessage",
    "RiskAssessmentResultMessage",
    "DetectedObject",
    "TrafficGroup",
    "SpatialFeatures",
    "MessageType",
    "TaskStatus",
    "RiskLevel",
    # Config
    "kafka_settings",
    "KafkaSettings",
    "TopicConfig",
    "DETECTION_RESULTS_TOPIC",
    "ASSESSMENT_TASKS_TOPIC",
    "RISK_ASSESSMENT_RESULTS_TOPIC",
    "DLQ_TOPIC",
    # API Key Pool
    "APIKeyPool",
    "APIKeyInfo",
    "KeyStatus",
    "create_key_pool_from_config",
    # Scheduler
    "TaskScheduler",
    "RateLimitException",
]
