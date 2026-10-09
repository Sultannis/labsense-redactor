"""JSON log lines. What may be logged: the endpoint, status, timing, page and region counts, the
types found and fixed reason codes. Never document text, detected details, known details, storage
keys or tokens; request bodies aren't logged at all."""

import json
import logging
import sys
import time
from typing import Any

_FIELDS = ("endpoint", "status", "ms", "pages", "regions", "types", "scanned", "verified", "reason", "error")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        for field in _FIELDS:
            if hasattr(record, field):
                line[field] = getattr(record, field)
        return json.dumps(line, ensure_ascii=False)


def configure(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn's access log would repeat every request; its error log keeps our format.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
