"""Manage active detection sessions for cameras."""

from __future__ import annotations

import threading
from typing import Callable, Dict, Optional

from loguru import logger

from algo.llm.dangerous_driving_detector import DangerousDrivingAnalyzer
from algo.rtsp_detect.group_analyzer import GroupAnalyzer
from algo.rtsp_detect.pipeline import DetectionPipeline
from algo.rtsp_detect.video_stream import VideoStream
from algo.rtsp_detect.yolo_detector import YoloDetector

# Kafka integration (optional)
try:
    from algo.kafka.detection_producer import DetectionResultProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("Kafka module not available for SessionManager")


class CameraSession:
    def __init__(
        self,
        camera_id: int,
        stream: VideoStream,
        pipeline: DetectionPipeline,
    ) -> None:
        self.camera_id = camera_id
        self.stream = stream
        self.pipeline = pipeline

    def stop(self) -> None:
        self.pipeline.stop()


class SessionManager:
    """Coordinates active camera detection pipelines."""

    def __init__(
        self,
        detector: YoloDetector,
        frame_interval: float,
        group_analyzer: Optional[GroupAnalyzer] = None,
        dangerous_analyzer_factory: Optional[Callable[[], DangerousDrivingAnalyzer]] = None,
        kafka_producer: Optional['DetectionResultProducer'] = None,
        enable_kafka: bool = False,
    ) -> None:
        self.detector = detector
        self.frame_interval = frame_interval
        self.group_analyzer = group_analyzer
        self.dangerous_analyzer_factory = dangerous_analyzer_factory
        self.kafka_producer = kafka_producer
        self.enable_kafka = enable_kafka and KAFKA_AVAILABLE
        
        if self.enable_kafka and not self.kafka_producer:
            logger.warning("Kafka enabled but no producer provided to SessionManager")
            self.enable_kafka = False
        elif self.enable_kafka:
            logger.info("SessionManager initialized with Kafka streaming support")
        
        self._sessions: Dict[int, CameraSession] = {}
        self._lock = threading.Lock()

    def start_session(self, camera_id: int, source: str, callback: Callable[[Dict], None]) -> None:
        with self._lock:
            if camera_id in self._sessions:
                logger.info("Camera {} already has an active session; restarting", camera_id)
                self._sessions[camera_id].stop()
                del self._sessions[camera_id]

            stream = VideoStream(source=source, name=str(camera_id))
            pipeline = DetectionPipeline(
                camera_id,
                stream,
                self.detector,
                self.frame_interval,
                callback,
                group_analyzer=self.group_analyzer,
                dangerous_analyzer=self.dangerous_analyzer_factory() if self.dangerous_analyzer_factory else None,
                kafka_producer=self.kafka_producer,
                enable_kafka=self.enable_kafka,
            )
            pipeline.start()
            self._sessions[camera_id] = CameraSession(camera_id, stream, pipeline)

    def stop_session(self, camera_id: int) -> None:
        with self._lock:
            session = self._sessions.pop(camera_id, None)
        if session:
            session.stop()
            logger.info("Stopped session for camera {}", camera_id)

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop()

    def has_session(self, camera_id: int) -> bool:
        with self._lock:
            return camera_id in self._sessions

    @staticmethod
    def check_camera(source: str, timeout: float = 5.0) -> bool:
        return VideoStream.probe(source, timeout=timeout)
