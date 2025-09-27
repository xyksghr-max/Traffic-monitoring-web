"""Manual test script for streaming detection via WebSocket."""

from __future__ import annotations

import json
import os
import time
from contextlib import closing
from typing import Any, Dict

from websocket import create_connection

WS_URL = os.getenv("ALGO_WS_URL", "ws://localhost:5000/ws")
VIDEO_SOURCE = os.getenv(
    "ALGO_TEST_VIDEO",
    r"D:\\traffic-monitoring-web\\other\\camera\\video\\video_1.mp4",
)
CAMERA_ID = int(os.getenv("ALGO_TEST_CAMERA_ID", "101"))


def send_message(ws, message: Dict[str, Any]) -> None:
    ws.send(json.dumps(message))


def main() -> None:
    print(f"Connecting to {WS_URL}")
    with closing(create_connection(WS_URL, timeout=10)) as ws:
        welcome = json.loads(ws.recv())
        print("Welcome:", welcome)

        print("Checking camera source...")
        send_message(
            ws,
            {
                "type": "check_camera",
                "data": {
                    "cameraId": CAMERA_ID,
                    "rtspUrl": VIDEO_SOURCE,
                },
            },
        )
        status_msg = json.loads(ws.recv())
        print("Camera status:", status_msg)

        print("Starting stream...")
        send_message(
            ws,
            {
                "type": "start_stream",
                "data": {
                    "cameraId": CAMERA_ID,
                    "rtspUrl": VIDEO_SOURCE,
                },
            },
        )

        detection_count = 0
        start_time = time.time()
        try:
            while detection_count < 3 and time.time() - start_time < 60:
                raw = ws.recv()
                if raw is None:
                    print("Connection closed by server")
                    break
                message = json.loads(raw)
                msg_type = message.get("type")
                data = message.get("data", {})
                if msg_type == "detection_result":
                    detection_count += 1
                    objects = data.get("detectedObjects", [])
                    print(
                        f"Detection #{detection_count}: objects={len(objects)},"
                        f" processTime={data.get('processTime', 0.0):.3f}s"
                    )
                elif msg_type == "camera_status":
                    print("Camera status update:", data)
                elif msg_type == "stream_stopped":
                    print("Stream stopped:", data)
                    break
                elif msg_type == "pong":
                    continue
                else:
                    print("Received message:", message)
        finally:
            print("Stopping stream...")
            send_message(
                ws,
                {
                    "type": "stop_stream",
                    "data": {
                        "cameraId": CAMERA_ID,
                    },
                },
            )
            # absorb acknowledgment messages
            ws.settimeout(2)
            try:
                while True:
                    raw = ws.recv()
                    if raw is None:
                        break
                    print("Post-stop message:", json.loads(raw))
            except Exception:
                pass

        print(f"Received {detection_count} detection results")


if __name__ == "__main__":
    main()
