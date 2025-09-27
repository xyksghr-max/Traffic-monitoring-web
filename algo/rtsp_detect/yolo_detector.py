"""YOLO detector wrapper."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from loguru import logger
from ultralytics import YOLO

from config import settings


class YoloDetector:
    """Encapsulate YOLO model loading and inference."""

    def __init__(self, config_path: Path, weights_dir: Path, allowed_classes: Optional[List[str]] = None) -> None:
        self.config = self._load_config(config_path)
        model_cfg = self.config.get("model", {})
        model_name = model_cfg.get("name", "yolov8n.pt")
        weights_path = weights_dir / model_name

        self.model = None
        self._model_available = False
        self._warned_unavailable = False
        self.model_type = model_name

        try:
            if weights_path.exists():
                logger.info("Loading YOLO weights from %s", weights_path)
                self.model = YOLO(str(weights_path))
            else:
                logger.warning(
                    "Model weights %s not found locally; provide weights to avoid slow start."
                    " Attempting to load model by name, which may trigger a download.",
                    weights_path,
                )
                self.model = YOLO(model_name)
            self._model_available = True
        except Exception as exc:  # pragma: no cover - requires runtime resources
            logger.exception("Failed to load YOLO model: %s", exc)
            self.model = None
            self._model_available = False

        if self._model_available and self.model is not None:
            device = model_cfg.get("device", "cpu")
            try:
                self.model.to(device)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to move YOLO model to %s: %s", device, exc)
            try:
                self.model.fuse()
            except Exception:
                pass

        self.confidence_threshold = float(model_cfg.get("confidence_threshold", 0.35))
        self.iou_threshold = float(model_cfg.get("iou_threshold", 0.5))
        self.max_det = int(model_cfg.get("max_det", 200))

        classes_section = self.config.get("classes", {})
        include_list = classes_section.get("include")
        self.allowed_classes = set(allowed_classes or include_list or settings.allowed_classes)

        if self.allowed_classes:
            self.supported_classes = sorted(self.allowed_classes)
        elif self._model_available and self.model is not None:
            self.supported_classes = [self.model.names[int(i)] for i in range(len(self.model.names))]
        else:
            self.supported_classes = []

    @staticmethod
    def _load_config(path: Path) -> Dict:
        if not path.exists():
            logger.warning("Model config %s does not exist; using defaults.", path)
            return {}
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def detect(self, frame) -> Dict[str, any]:
        if not self._model_available or self.model is None:
            if not self._warned_unavailable:
                logger.error("YOLO model is unavailable; returning empty detection results.")
                self._warned_unavailable = True
            return {"objects": [], "latency": 0.0}

        start_time = time.time()
        results = self.model.predict(
            source=frame,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            max_det=self.max_det,
            verbose=False,
        )
        elapsed = time.time() - start_time

        detections: List[Dict] = []
        if not results:
            return {
                "objects": detections,
                "latency": elapsed,
            }

        result = results[0]
        if not hasattr(result, "boxes"):
            return {
                "objects": detections,
                "latency": elapsed,
            }

        boxes = result.boxes
        for box in boxes:
            cls_idx = int(box.cls.item()) if hasattr(box.cls, "item") else int(box.cls)
            class_name = self.model.names.get(cls_idx, str(cls_idx)) if self.model else str(cls_idx)
            if self.allowed_classes and class_name not in self.allowed_classes:
                continue
            xyxy = box.xyxy[0].tolist()
            detections.append(
                {
                    "class": class_name,
                    "confidence": float(box.conf.item()) if hasattr(box.conf, "item") else float(box.conf),
                    "bbox": [float(x) for x in xyxy],
                    "level": 0,
                }
            )

        return {
            "objects": detections,
            "latency": elapsed,
        }
