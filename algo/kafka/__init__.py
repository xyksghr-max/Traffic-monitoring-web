"""Kafka integration module for streaming detection results."""

from algo.kafka.detection_producer import DetectionResultProducer
from algo.kafka.base_consumer import BaseKafkaConsumer

__all__ = ['DetectionResultProducer', 'BaseKafkaConsumer']
