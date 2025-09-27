"""Utilities for analyzing detected object groups in traffic scenes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from utils.image import encode_frame_to_base64


@dataclass
class GroupAnalyzerConfig:
    distance_threshold: float = 150.0
    min_group_size: int = 2
    crop_margin: int = 12


class GroupAnalyzer:
    """Cluster detected objects that are spatially close to each other."""

    def __init__(self, config: GroupAnalyzerConfig | None = None) -> None:
        self.config = config or GroupAnalyzerConfig()

    def analyze(
        self,
        frame: np.ndarray,
        detections: Sequence[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        if len(detections) < self.config.min_group_size:
            return [], []

        parents = list(range(len(detections)))

        def find(x: int) -> int:
            while parents[x] != x:
                parents[x] = parents[parents[x]]
                x = parents[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parents[ra] = rb

        centers = [self._center(det["bbox"]) for det in detections]

        for i in range(len(detections)):
            for j in range(i + 1, len(detections)):
                if self._distance(centers[i], centers[j]) <= self.config.distance_threshold:
                    union(i, j)

        clusters: Dict[int, List[int]] = {}
        for idx in range(len(detections)):
            root = find(idx)
            clusters.setdefault(root, []).append(idx)

        groups: List[Dict] = []
        group_images: List[Dict] = []

        for indexes in clusters.values():
            if len(indexes) < self.config.min_group_size:
                continue
            selected = [detections[i] for i in indexes]
            bbox = self._merge_bboxes([det["bbox"] for det in selected])
            group_dict = {
                "groupIndex": len(groups) + 1,
                "objectCount": len(selected),
                "bbox": bbox,
                "classes": sorted({det["class"] for det in selected}),
                "averageConfidence": float(sum(det.get("confidence", 0.0) for det in selected) / len(selected)),
            }
            groups.append(group_dict)

            crop = self._crop_frame(frame, bbox, self.config.crop_margin)
            if crop.size != 0:
                data_uri, _ = encode_frame_to_base64(crop)
                base64_part = data_uri.split(",", 1)[1] if "," in data_uri else data_uri
                group_images.append(
                    {
                        "groupIndex": group_dict["groupIndex"],
                        "imageBase64": base64_part,
                        "bbox": bbox,
                        "objectCount": group_dict["objectCount"],
                        "classes": group_dict["classes"],
                    }
                )

        return groups, group_images

    @staticmethod
    def _center(bbox: Sequence[float]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return (float(x1 + x2) / 2.0, float(y1 + y2) / 2.0)

    @staticmethod
    def _distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return float(np.linalg.norm(np.array(p1) - np.array(p2)))

    @staticmethod
    def _merge_bboxes(boxes: Sequence[Sequence[float]]) -> List[float]:
        x1 = min(box[0] for box in boxes)
        y1 = min(box[1] for box in boxes)
        x2 = max(box[2] for box in boxes)
        y2 = max(box[3] for box in boxes)
        return [float(x1), float(y1), float(x2), float(y2)]

    @staticmethod
    def _crop_frame(frame: np.ndarray, bbox: Sequence[float], margin: int) -> np.ndarray:
        h, w = frame.shape[:2]
        x1 = int(max(0, bbox[0] - margin))
        y1 = int(max(0, bbox[1] - margin))
        x2 = int(min(w, bbox[2] + margin))
        y2 = int(min(h, bbox[3] + margin))
        if x1 >= x2 or y1 >= y2:
            return np.zeros((0, 0, 3), dtype=frame.dtype)
        return frame[y1:y2, x1:x2]
