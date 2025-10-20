"""Kafka configuration and topic definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


@dataclass
class TopicConfig:
    """Configuration for a Kafka topic."""
    name: str
    partitions: int
    replication_factor: int
    retention_ms: int = 86400000  # 24 hours
    compression_type: str = "snappy"
    cleanup_policy: str = "delete"
    
    def to_admin_config(self) -> Dict[str, str]:
        """Convert to Kafka admin API config format."""
        return {
            "retention.ms": str(self.retention_ms),
            "compression.type": self.compression_type,
            "cleanup.policy": self.cleanup_policy,
        }


# Topic definitions
DETECTION_RESULTS_TOPIC = TopicConfig(
    name="detection-results-topic",
    partitions=16,
    replication_factor=3,
    retention_ms=3600000,  # 1 hour (detection data is transient)
    compression_type="snappy",
)

ASSESSMENT_TASKS_TOPIC = TopicConfig(
    name="assessment-tasks-topic",
    partitions=32,
    replication_factor=3,
    retention_ms=7200000,  # 2 hours
    compression_type="snappy",
)

RISK_ASSESSMENT_RESULTS_TOPIC = TopicConfig(
    name="risk-assessment-results-topic",
    partitions=16,
    replication_factor=3,
    retention_ms=86400000,  # 24 hours (results need longer retention)
    compression_type="snappy",
)

# Dead letter queue for failed messages
DLQ_TOPIC = TopicConfig(
    name="failed-messages-dlq",
    partitions=4,
    replication_factor=3,
    retention_ms=604800000,  # 7 days
    compression_type="lz4",
)

ALL_TOPICS = [
    DETECTION_RESULTS_TOPIC,
    ASSESSMENT_TASKS_TOPIC,
    RISK_ASSESSMENT_RESULTS_TOPIC,
    DLQ_TOPIC,
]


class KafkaSettings(BaseSettings):
    """Kafka configuration settings."""
    
    # Kafka cluster
    kafka_bootstrap_servers: str = Field(
        "localhost:9092",
        description="Comma-separated list of Kafka broker addresses"
    )
    kafka_security_protocol: str = Field(
        "PLAINTEXT",
        description="Security protocol (PLAINTEXT, SASL_SSL, etc.)"
    )
    kafka_sasl_mechanism: Optional[str] = Field(
        None,
        description="SASL mechanism (PLAIN, SCRAM-SHA-256, etc.)"
    )
    kafka_sasl_username: Optional[str] = None
    kafka_sasl_password: Optional[str] = None
    
    # Producer settings
    kafka_producer_acks: str = Field(
        "all",
        description="Number of acknowledgments (0, 1, all)"
    )
    kafka_producer_retries: int = Field(
        3,
        description="Number of retries for failed sends"
    )
    kafka_producer_batch_size: int = Field(
        65536,
        description="Batch size in bytes"
    )
    kafka_producer_linger_ms: int = Field(
        10,
        description="Time to wait for batching"
    )
    kafka_producer_compression_type: str = Field(
        "snappy",
        description="Compression type (none, gzip, snappy, lz4, zstd)"
    )
    kafka_producer_max_in_flight: int = Field(
        5,
        description="Max in-flight requests per connection"
    )
    
    # Consumer settings
    kafka_consumer_group_id: str = Field(
        "traffic-monitoring-consumers",
        description="Consumer group ID"
    )
    kafka_consumer_auto_offset_reset: str = Field(
        "latest",
        description="Offset reset strategy (earliest, latest)"
    )
    kafka_consumer_enable_auto_commit: bool = Field(
        False,
        description="Enable auto-commit (prefer manual commit for exactly-once)"
    )
    kafka_consumer_max_poll_records: int = Field(
        500,
        description="Max records per poll"
    )
    kafka_consumer_session_timeout_ms: int = Field(
        30000,
        description="Session timeout in milliseconds"
    )
    kafka_consumer_heartbeat_interval_ms: int = Field(
        10000,
        description="Heartbeat interval in milliseconds"
    )
    
    # Connection settings
    kafka_request_timeout_ms: int = Field(
        30000,
        description="Request timeout in milliseconds"
    )
    kafka_connections_max_idle_ms: int = Field(
        540000,
        description="Max idle time for connections"
    )
    
    model_config = {
        "env_prefix": "KAFKA_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
    
    def get_producer_config(self) -> Dict[str, any]:
        """Get Kafka producer configuration."""
        config = {
            "bootstrap_servers": self.kafka_bootstrap_servers.split(","),
            "acks": self.kafka_producer_acks,
            "retries": self.kafka_producer_retries,
            "batch_size": self.kafka_producer_batch_size,
            "linger_ms": self.kafka_producer_linger_ms,
            "compression_type": self.kafka_producer_compression_type,
            "max_in_flight_requests_per_connection": self.kafka_producer_max_in_flight,
            "request_timeout_ms": self.kafka_request_timeout_ms,
            "connections_max_idle_ms": self.kafka_connections_max_idle_ms,
            "security_protocol": self.kafka_security_protocol,
        }
        
        if self.kafka_sasl_mechanism:
            config["sasl_mechanism"] = self.kafka_sasl_mechanism
            config["sasl_plain_username"] = self.kafka_sasl_username
            config["sasl_plain_password"] = self.kafka_sasl_password
        
        return config
    
    def get_consumer_config(self, group_id: Optional[str] = None) -> Dict[str, any]:
        """Get Kafka consumer configuration."""
        config = {
            "bootstrap_servers": self.kafka_bootstrap_servers.split(","),
            "group_id": group_id or self.kafka_consumer_group_id,
            "auto_offset_reset": self.kafka_consumer_auto_offset_reset,
            "enable_auto_commit": self.kafka_consumer_enable_auto_commit,
            "max_poll_records": self.kafka_consumer_max_poll_records,
            "session_timeout_ms": self.kafka_consumer_session_timeout_ms,
            "heartbeat_interval_ms": self.kafka_consumer_heartbeat_interval_ms,
            "request_timeout_ms": self.kafka_request_timeout_ms,
            "connections_max_idle_ms": self.kafka_connections_max_idle_ms,
            "security_protocol": self.kafka_security_protocol,
        }
        
        if self.kafka_sasl_mechanism:
            config["sasl_mechanism"] = self.kafka_sasl_mechanism
            config["sasl_plain_username"] = self.kafka_sasl_username
            config["sasl_plain_password"] = self.kafka_sasl_password
        
        return config


# Global settings instance
kafka_settings = KafkaSettings()
