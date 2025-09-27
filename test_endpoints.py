"""Basic smoke tests for the algorithm service HTTP and WebSocket endpoints."""

from __future__ import annotations

import json
from contextlib import closing

import requests
from websocket import create_connection

BASE_URL = "http://localhost:5000"


def test_health_endpoint() -> None:
    url = f"{BASE_URL}/api/health/health_check"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    payload = resp.json()
    assert payload["code"] == 200
    assert payload["data"]["status"] == "UP"
    print("HTTP health check OK", json.dumps(payload, ensure_ascii=False))


def test_websocket() -> None:
    ws_url = "ws://localhost:5000/ws"
    with closing(create_connection(ws_url, timeout=5)) as ws:
        welcome = json.loads(ws.recv())
        assert welcome["type"] == "connection_ack"
        ws.send(json.dumps({"type": "ping"}))
        pong = json.loads(ws.recv())
        assert pong["type"] == "pong"
        print("WebSocket handshake OK", welcome, pong)


if __name__ == "__main__":
    test_health_endpoint()
    test_websocket()
