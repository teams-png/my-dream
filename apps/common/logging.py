import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    SAFE_FIELDS = ("request_id", "method", "path", "status", "duration_ms", "user_id", "company_id")

    def format(self, record):
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        payload.update({key: getattr(record, key) for key in self.SAFE_FIELDS if hasattr(record, key)})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
