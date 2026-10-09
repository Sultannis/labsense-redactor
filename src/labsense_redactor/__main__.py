"""`python -m labsense_redactor`: the HTTP server on port 8000 (`PORT`)."""

import os

import uvicorn

from . import logs


def main() -> None:
    logs.configure(os.environ.get("LOG_LEVEL", "INFO").upper())
    uvicorn.run(
        "labsense_redactor.app:create_app",
        factory=True,
        host=os.environ.get("HOST", "0.0.0.0"),  # noqa: S104 - a container, reached only inside the VPC
        port=int(os.environ.get("PORT", "8000")),
        workers=int(os.environ.get("WEB_CONCURRENCY", "1")),
        access_log=False,
        log_config=None,
        server_header=False,
        date_header=False,
    )


if __name__ == "__main__":
    main()
