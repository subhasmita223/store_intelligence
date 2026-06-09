"""Structured JSON request logging middleware. T-23."""

import json
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id

        start = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000)

        # extract store_id from path like /stores/{store_id}/...
        path_parts = request.url.path.split("/")
        store_id = None
        if "stores" in path_parts:
            idx = path_parts.index("stores")
            if idx + 1 < len(path_parts):
                store_id = path_parts[idx + 1]

        event_count = None
        if request.url.path == "/events/ingest" and request.method == "POST":
            event_count = getattr(request.state, "accepted_count", None)

        log = {
            "trace_id": trace_id,
            "store_id": store_id,
            "endpoint": request.url.path,
            "method": request.method,
            "latency_ms": latency_ms,
            "event_count": event_count,
            "status_code": response.status_code,
        }
        print(json.dumps(log), flush=True)

        response.headers["X-Trace-Id"] = trace_id
        return response
