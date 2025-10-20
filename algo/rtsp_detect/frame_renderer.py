"""Utilities to render detection results directly on video frames."""

from __future__ import annotations

from typing import Dict, Sequence

import cv2
import numpy as np


OBJECT_COLOR = (0, 0, 255)  # 红色（BGR）
GROUP_COLORS = {
    "blue": (255, 0, 0),       # 高风险 → 蓝色
    "orange": (0, 165, 255),   # 中风险 → 橙色
    "yellow": (0, 255, 255),   # 低风险 → 亮黄色
    "gray": (200, 200, 200),   # 无风险 → 灰色
    "none": (200, 200, 200),
    "default": (0, 215, 255),
}
OBJECT_THICKNESS = 2
GROUP_THICKNESS = 3
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.5
FONT_THICKNESS = 1


def render_frame(
    frame: np.ndarray,
    detections: Sequence[Dict],
    groups: Sequence[Dict],
) -> np.ndarray:
    """Draw detected objects and traffic groups on the provided frame.

    Parameters
    ----------
    frame:
        Numpy array representing the BGR image to draw on.
    detections:
        List of detection dicts containing `bbox`, `class`, and `confidence`.
    groups:
        List of group dicts containing `bbox`/`groupBbox`, `groupIndex`,
        and optional `riskLevel`.
    """
    output = frame.copy()
    _draw_detections(output, detections)
    _draw_groups(output, groups)
    return output


def _draw_detections(frame: np.ndarray, detections: Sequence[Dict]) -> None:
    for det in detections:
        bbox = det.get("bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = _to_int_bbox(bbox)

        cv2.rectangle(frame, (x1, y1), (x2, y2), OBJECT_COLOR, OBJECT_THICKNESS)

        label = det.get("class", "")
        confidence = det.get("confidence")
        if confidence is not None:
            label = f"{label} {confidence * 100:.0f}%"

        _draw_label(frame, (x1, y1), label, OBJECT_COLOR)


def _draw_groups(frame: np.ndarray, groups: Sequence[Dict]) -> None:
    for group in groups:
        bbox = group.get("groupBbox") or group.get("bbox")
        if not bbox:
            continue

        x1, y1, x2, y2 = _to_int_bbox(bbox)

        risk_level = str(group.get("riskLevel", "default")).lower()
        color = GROUP_COLORS.get(risk_level, GROUP_COLORS["default"])
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, GROUP_THICKNESS)

        index = group.get("groupIndex", "")
        object_count = group.get("objectCount") or group.get("memberCount")

        risk_label_map = {
            "blue": "High",
            "orange": "Medium",
            "yellow": "Low",
            "gray": "None",
            "none": "None",
        }

        label_parts: list[str] = [f"Group {index}"]
        if object_count:
            try:
                count_int = int(object_count)
            except (TypeError, ValueError):
                count_int = object_count
            label_parts.append(f"{count_int} objs")

        label_parts.append(risk_label_map.get(risk_level, "Unknown"))

        label = " | ".join(str(part) for part in label_parts if part)
        _draw_label(frame, (x1, y1), label, color)


def _draw_label(frame: np.ndarray, origin: tuple[int, int], text: str, color: tuple[int, int, int]) -> None:
    if not text:
        return

    x, y = origin
    text_size, baseline = cv2.getTextSize(text, FONT, FONT_SCALE, FONT_THICKNESS)
    text_width, text_height = text_size
    top = max(y, text_height + baseline + 4)

    cv2.rectangle(
        frame,
        (x, top - text_height - baseline - 2),
        (x + text_width + 6, top + baseline),
        color,
        -1,
    )
    cv2.putText(
        frame,
        text,
        (x + 3, top - 4),
        FONT,
        FONT_SCALE,
        (0, 0, 0),
        FONT_THICKNESS,
        lineType=cv2.LINE_AA,
    )


def _to_int_bbox(bbox: Sequence[float]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    return int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
