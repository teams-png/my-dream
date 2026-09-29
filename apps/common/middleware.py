import logging
import time
import uuid

logger = logging.getLogger("requests")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:100]
        started = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        logger.info("request_complete", extra={
            "request_id": request.request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "user_id": getattr(getattr(request, "user", None), "id", None),
            "company_id": getattr(getattr(request, "company", None), "id", None),
        })
        return response
