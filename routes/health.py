"""Health check endpoint blueprints.

This module exposes two endpoints for health checks:

- Legacy:   GET /api/health/health_check -> wrapped response { code, msg, data: {...} }
- Frontend: GET /health/health_check     -> flat response   { status, service, version }

Both share the same underlying health information but differ in response shape
to remain backward compatible while supporting the new frontend contract.
"""

from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path
import re

from flask import Blueprint, jsonify

from config import settings
from utils.response import success

bp = Blueprint("health", __name__)
# Public blueprint without /api prefix for the new frontend contract
bp_public = Blueprint("health_public", __name__)


def _load_version_from_pyproject() -> str:
    """Load version string from pyproject.toml without hard dependency.

    Preference order:
    1) stdlib tomllib (Python 3.11+)
    2) third-party tomli
    3) lightweight regex under [project] section
    """
    root = Path(__file__).resolve().parent.parent
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0"

    # Try tomllib (3.11+)
    try:  # pragma: no cover - env specific
        import tomllib  # type: ignore

        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        return str(data.get("project", {}).get("version", "0.0.0"))
    except Exception:
        pass

    # Try tomli
    try:  # pragma: no cover - env specific
        import tomli  # type: ignore

        with pyproject.open("rb") as f:
            data = tomli.load(f)
        return str(data.get("project", {}).get("version", "0.0.0"))
    except Exception:
        pass

    # Fallback: simple regex only within [project]
    try:
        text = pyproject.read_text(encoding="utf-8", errors="ignore").splitlines()
        in_project = False
        version_re = re.compile(r"^\s*version\s*=\s*['\"]([^'\"]+)['\"]\s*$")
        for line in text:
            if line.strip().startswith("[") and line.strip().endswith("]"):
                in_project = line.strip() == "[project]"
                continue
            if in_project:
                m = version_re.match(line)
                if m:
                    return m.group(1)
    except Exception:
        pass

    return "0.0.0"


# Cache version at import time
VERSION = _load_version_from_pyproject()


def _health_summary() -> dict:
    """Minimal health data expected by the frontend contract."""
    return {
        "status": "ok",
        "service": "algo",
        "version": VERSION,
    }


@bp.get("/health_check")
def health_check():
    """Return service health information for readiness probes."""
    data = {
        "status": "ok",
        "service": "algo",
        "version": VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "frame_interval": settings.frame_interval,
        },
    }
    return success(data=data)


@bp_public.get("/health_check")
def health_check_public():
    """Return the simplified health payload for frontend consumption."""
    return jsonify(_health_summary()), 200
