"""Errors the service answers with. Their codes are fixed strings: never document text."""


class Unprocessable(Exception):
    """The request is well-formed, but the document can't be processed (HTTP 422)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
