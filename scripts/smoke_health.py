import threading
import time
from contextlib import contextmanager
import sys
import os

import requests
from werkzeug.serving import make_server

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app as app_module  # type: ignore
from app import app  # type: ignore


@contextmanager
def run_server(host: str = "127.0.0.1", port: int = 5000):
    server = make_server(host, port, app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        thread.join(timeout=3)


def main():
    with run_server():
        r1 = requests.get("http://127.0.0.1:5000/health/health_check", timeout=5)
        print("/health/health_check:", r1.status_code, r1.json())
        r2 = requests.get("http://127.0.0.1:5000/api/health/health_check", timeout=5)
        print("/api/health/health_check:", r2.status_code, r2.json())


if __name__ == "__main__":
    main()
