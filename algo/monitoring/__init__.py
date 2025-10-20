"""Monitoring module for Prometheus metrics."""

from algo.monitoring.metrics import *

__all__ = [
    # Metrics
    'detection_total',
    'detection_latency',
    'detected_objects_total',
    'traffic_groups_total',
    'kafka_messages_sent',
    'kafka_messages_received',
    'kafka_send_errors',
    'kafka_lag',
    'llm_requests_total',
    'llm_latency',
    'llm_token_usage',
    'llm_concurrent_tasks',
    'api_key_pool_size',
    'api_key_status',
    'api_key_success_rate',
    'api_key_total_calls',
    'api_key_cooldown_seconds',
    'tasks_generated',
    'tasks_processed',
    'task_queue_size',
    'risk_alerts_total',
    'risk_types_detected',
    'active_cameras',
    'pipeline_errors',
    'system_info',
    # Helper functions
    'record_detection',
    'record_kafka_send',
    'record_llm_request',
    'update_api_key_pool_metrics',
    'record_risk_alert',
]
