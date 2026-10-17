from core.utils.constants import STATUS_REASONS

class HTTPRequestError(Exception):
    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or STATUS_REASONS.get(status, "Error"))
        self.status = status