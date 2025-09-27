"""Application entry point for the traffic monitoring algorithm service."""

from __future__ import annotations

import os
from typing import Any

from flask import Flask
from flask_cors import CORS
from flask_sock import Sock
from loguru import logger

from config import settings
from routes.health import bp as health_bp
from routes.ws import register_ws_routes
from utils.logger import configure_logging

sock = Sock()


def create_app() -> Flask:
    """Application factory used by both CLI and WSGI servers."""
    configure_logging()

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB uploads cap

    # Enable CORS for API endpoints; adjust origins via env if necessary
    allowed_origins = os.getenv("ALGO_CORS_ORIGINS", "*")
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    # Register HTTP blueprints
    app.register_blueprint(health_bp, url_prefix="/api/health")

    # Attach WebSocket routes
    sock.init_app(app)
    register_ws_routes(sock)

    logger.info(
        "Algorithm service initialised on {}:{}",
        settings.server_host,
        settings.server_port,
    )

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    app.run(host=settings.server_host, port=settings.server_port, debug=False)
