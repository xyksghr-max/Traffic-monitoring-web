"""Health check endpoint blueprint."""

from __future__ import annotations

import platform
from datetime import datetime

from flask import Blueprint

from config import settings
from utils.response import success

bp = Blueprint("health", __name__)


@bp.get("/health_check")
def health_check():
    """Return service health information for readiness probes."""
    data = {
        "status": "UP",
        "service": "algo",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "frame_interval": settings.frame_interval,
        },
    }
    return success(data=data)
