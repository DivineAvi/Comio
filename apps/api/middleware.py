"""Custom middleware for the Comio API.

Middleware runs on EVERY request — before and after your route code.
Unlike Depends() (which is per-route), middleware is global.
"""

import uuid
import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique request ID to every request and response.

    Why this matters:
    - In production, thousands of requests happen per second
    - When something fails, you need to find THAT specific request in the logs
    - The request ID ties together: the log entry, the error, and the response

    The ID is:
    - Generated if not provided by the client
    - Added to the response headers (so the frontend can see it)
    - Logged with every log message for this request
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID (for tracing across services) or generate one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])

        # Record start time for request duration logging
        start_time = time.time()

        # Process the request (runs your route code)
        response = await call_next(request)

        # Calculate how long the request took
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Add request ID and timing to response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Log every request (method, path, status, duration)
        logger.info(
            "[%s] %s %s → %s (%sms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response