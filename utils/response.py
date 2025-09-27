"""Utility helpers for building API responses in a consistent format."""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import jsonify


def success(data: Optional[Dict[str, Any]] = None, msg: str = "OK", code: int = 200):
    """Return a standardized success response."""
    payload = {"code": code, "msg": msg, "data": data or {}}
    return jsonify(payload), 200


def error(msg: str, code: int = 500, data: Optional[Dict[str, Any]] = None):
    """Return a standardized error response."""
    payload = {"code": code, "msg": msg, "data": data or {}}
    return jsonify(payload), code
