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
    ) -> None:
        self.detector = detector
        self.frame_interval = frame_interval
        self.group_analyzer = group_analyzer
        self.dangerous_analyzer_factory = dangerous_analyzer_factory
        self._sessions: Dict[int, CameraSession] = {}
        self._lock = threading.Lock()

    def start_session(self, camera_id: int, source: str, callback: Callable[[Dict], None]) -> None:
        with self._lock:
            if camera_id in self._sessions:
                logger.info("Camera %s already has an active session; restarting", camera_id)
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
            )
            pipeline.start()
            self._sessions[camera_id] = CameraSession(camera_id, stream, pipeline)

    def stop_session(self, camera_id: int) -> None:
        with self._lock:
            session = self._sessions.pop(camera_id, None)
        if session:
            session.stop()
            logger.info("Stopped session for camera %s", camera_id)

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
