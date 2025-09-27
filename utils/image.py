"""Image encoding utilities."""

from __future__ import annotations

import base64
from typing import Tuple

import cv2
import numpy as np


def encode_frame_to_base64(frame: np.ndarray, format: str = "jpg", quality: int = 90) -> Tuple[str, bytes]:
    """Encode an image frame to base64 string with data URI prefix."""
    encode_param = []
    if format.lower() in {"jpg", "jpeg"}:
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(f".{format}", frame, encode_param)
    if not success:
        raise ValueError("Failed to encode frame to image format")
    encoded_bytes = base64.b64encode(buffer)
    data_uri = f"data:image/{format};base64," + encoded_bytes.decode("utf-8")
    return data_uri, buffer.tobytes()
