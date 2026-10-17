# Status Codes
STATUS_REASONS = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    413: "Content Too Large",
    431: "Request Header Fields Too Large"
}

# Server Setting
SETTINGS = {
    "HOST": "0.0.0.0",
    "PORT": 8080,
    "MAX_HEADER_BYTES": 64 * 1024,
    "KEEP_ALIVE_TIMEOUT": 30,  # 1min
    "MAX_REQUESTS_PER_CONNECTION": 100,
    "MAX_FILE_BYTES": 10 * 1024 * 1024,  # Max 10 MiB
    "ALLOWED_EXTENSIONS": {'.html', '.png', '.jpeg', '.jpg'},
}

