"""WebSocket route registration integrating detection pipeline."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict

from flask_sock import Sock
from loguru import logger

from algo.llm.dangerous_driving_detector import DangerousDrivingAnalyzer, DangerousDrivingConfig
from algo.rtsp_detect.group_analyzer import GroupAnalyzer, GroupAnalyzerConfig
from algo.rtsp_detect.session_manager import SessionManager
from algo.rtsp_detect.yolo_detector import YoloDetector
from config import settings

# Kafka integration (optional)
KAFKA_PRODUCER = None
if settings.enable_kafka_streaming:
    try:
        from algo.kafka.detection_producer import DetectionResultProducer
        KAFKA_PRODUCER = DetectionResultProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic='detection-results',
            enable_kafka=True
        )
        logger.info("Kafka producer initialized for streaming mode")
    except ImportError:
        logger.warning("Kafka module not available, streaming mode disabled")
    except Exception as exc:
        logger.error(f"Failed to initialize Kafka producer: {exc}")

WELCOME_MESSAGE: Dict[str, Any] = {
    "type": "connection_ack",
    "data": {
        "message": "WS connected (pipeline ready)",
    },
}

PING_RESPONSE: Dict[str, Any] = {
    "type": "pong",
    "data": {},
}

# Load YOLO model once at import time
DETECTOR = YoloDetector(settings.model_config_path, settings.weights_dir, settings.allowed_classes)


MODEL_CONFIG = DETECTOR.config or {}
POST_CFG = MODEL_CONFIG.get('post_processing', {})
GROUP_ANALYZER = GroupAnalyzer(
    GroupAnalyzerConfig(
        distance_threshold=float(POST_CFG.get('distance_threshold', 150.0)),
        min_group_size=int(POST_CFG.get('min_group_size', 2)),
        crop_margin=int(POST_CFG.get('crop_margin', 12)),
    )
)

LLM_CFG = MODEL_CONFIG.get('llm', {})
RISK_CFG = LLM_CFG.get('risk_threshold', {})
DANGEROUS_CONFIG = DangerousDrivingConfig(
    model=settings.llm_model,
    timeout=settings.llm_timeout,
    max_retry=settings.llm_max_retry,
    cooldown_seconds=float(LLM_CFG.get('cooldown_seconds', 3.0)),
    risk_threshold_low=float(RISK_CFG.get('low', 0.45)),
    risk_threshold_medium=float(RISK_CFG.get('medium', 0.65)),
    risk_threshold_high=float(RISK_CFG.get('high', 0.80)),
)


def _create_dangerous_analyzer() -> DangerousDrivingAnalyzer:
    """Factory producing analyzer instances per session."""
    enabled = bool(LLM_CFG.get('enabled', True))
    return DangerousDrivingAnalyzer(DANGEROUS_CONFIG, enabled=enabled)


def register_ws_routes(sock: Sock) -> None:
    """Register WebSocket endpoints on the provided Sock instance."""

    @sock.route("/ws")
    def websocket_gateway(ws):  # pragma: no cover - network interaction
        logger.info("WebSocket client connected")
        session_manager = SessionManager(
            DETECTOR,
            settings.frame_interval,
            group_analyzer=GROUP_ANALYZER,
            dangerous_analyzer_factory=_create_dangerous_analyzer,
            kafka_producer=KAFKA_PRODUCER,
            enable_kafka=settings.enable_kafka_streaming,
        )
        send_lock = threading.Lock()
        connection_closed = threading.Event()

        def send_message(message: Dict[str, Any]) -> None:
            if connection_closed.is_set():
                return
            try:
                payload = json.dumps(message)
            except TypeError as exc:
                logger.error("Failed to serialise WebSocket payload: %s", exc)
                return
            try:
                with send_lock:
                    ws.send(payload)
            except Exception as exc:  # pragma: no cover - network failures
                logger.exception("Failed to send WebSocket message: %s", exc)
                connection_closed.set()
                session_manager.stop_all()

        send_message(WELCOME_MESSAGE)

        try:
            while not connection_closed.is_set():
                raw_message = ws.receive()
                if raw_message is None:
                    logger.info("WebSocket client disconnected")
                    break

                logger.debug("Received WS message: %s", raw_message)

                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning("Received malformed JSON message; ignoring")
                    continue

                msg_type = message.get("type")
                data = message.get("data", {})

                if msg_type == "ping":
                    send_message(PING_RESPONSE)
                    continue

                if msg_type == "start_stream":
                    camera_id = data.get("cameraId")
                    source = data.get("rtspUrl")
                    if camera_id is None or not source:
                        logger.warning("start_stream missing cameraId or rtspUrl")
                        continue
                    session_manager.start_session(int(camera_id), source, send_message)
                    send_message(
                        {
                            "type": "camera_status",
                            "data": {
                                "cameraId": camera_id,
                                "status": 1,
                                "message": "Stream started",
                            },
                        }
                    )
                    continue

                if msg_type == "stop_stream":
                    camera_id = data.get("cameraId")
                    if camera_id is None:
                        continue
                    session_manager.stop_session(int(camera_id))
                    send_message(
                        {
                            "type": "stream_stopped",
                            "data": {
                                "cameraId": camera_id,
                                "reason": "Stopped by client",
                            },
                        }
                    )
                    continue

                if msg_type == "check_camera":
                    camera_id = data.get("cameraId")
                    source = data.get("rtspUrl")
                    ok = False
                    if source:
                        ok = SessionManager.check_camera(source)
                    send_message(
                        {
                            "type": "camera_status",
                            "data": {
                                "cameraId": camera_id,
                                "status": 1 if ok else 0,
                                "message": "Online" if ok else "Offline",
                            },
                        }
                    )
                    continue

                logger.warning("Unsupported message type received: %s", msg_type)

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("WebSocket handler error: %s", exc)
        finally:
            connection_closed.set()
            session_manager.stop_all()
            try:
                ws.close()
            except Exception:
                pass
            logger.info("WebSocket session terminated")
