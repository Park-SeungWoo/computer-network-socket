from __future__ import annotations

import threading
import socket
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit, unquote

from core.utils.constants import SETTINGS, STATUS_REASONS
from core.errors.http import HTTPRequestError
from core.utils.logs import log


class ClientConnection(threading.Thread):
    def __init__(
            self,
            name,
            client_socket: socket.socket,
            client_address: tuple[str, int],
            manager: "ConnectionManager",
            document_root: Path,
    ) -> None:
        super().__init__(
            name=name, daemon=True
        )
        self.connection_id = -1
        self.client_socket = client_socket
        self.client_address = client_address
        self.manager = manager
        self.document_root = document_root.resolve()
        self._buffer = bytearray()
        self._closed = threading.Event()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self.client_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.client_socket.close()
        except OSError:
            pass

    def run(self) -> None:
        try:
            self.client_socket.settimeout(SETTINGS['KEEP_ALIVE_TIMEOUT'])
            for _ in range(SETTINGS['MAX_REQUESTS_PER_CONNECTION']):
                try:
                    request = self._read_request()  # recv request
                    if request is None:
                        break

                    method, target, version, headers = request
                    keep_alive = self._should_keep_alive(version, headers)

                    if method != "GET":
                        self._send_response(
                            405,
                            b"Only GET is supported.\n",
                            "text/plain; charset=utf-8",
                            keep_alive=False,
                            extra_headers={"Allow": "GET"},
                        )
                        break

                    # send file
                    try:
                        file_path = self._resolve_file(target)
                        body = file_path.read_bytes()
                        if len(body) > SETTINGS['MAX_FILE_BYTES']:
                            raise HTTPRequestError(413)
                        content_type = self._content_type(file_path)
                        self._send_response(200, body, content_type, keep_alive)
                    except FileNotFoundError:
                        self._send_response(
                            404,
                            b"404 Not Found\n",
                            "text/plain; charset=utf-8",
                            keep_alive,
                        )

                except HTTPRequestError as error:  # req error handling
                    body = (
                        f"{error.status} {STATUS_REASONS[error.status]}\n"
                    ).encode("utf-8")
                    self._send_response(
                        error.status,
                        body,
                        "text/plain; charset=utf-8",
                        keep_alive=False,
                    )
                    break

                if not keep_alive:  # connection: close from cli -> close
                    break
        except socket.timeout:
            pass
        except (ConnectionError, OSError):
            pass
        finally:
            log(
                f"-{self.connection_id}-Close connection: {self.client_address[0]}:{self.client_address[1]}",
                "light-green",
            )
            self.close()
            self.manager.discard(self)

    def _read_request(self) -> tuple[str, str, str, dict[str, str]] | None:
        marker = b"\r\n\r\n"
        while marker not in self._buffer:
            if len(self._buffer) >= SETTINGS['MAX_HEADER_BYTES']:
                raise HTTPRequestError(431)
            try:
                chunk = self.client_socket.recv(4096)
            except socket.timeout:
                if self._buffer:
                    raise HTTPRequestError(408)
                return None
            if not chunk:
                return None
            self._buffer.extend(chunk)

        header_end = self._buffer.index(marker)
        raw_headers = bytes(self._buffer[:header_end])
        del self._buffer[: header_end + len(marker)]

        try:
            lines = raw_headers.decode("utf-8").split("\r\n")
            parts = lines[0].split()
            if len(parts) != 3:
                raise ValueError("Malformed request line")
            method, target, version = parts
            if version not in ("HTTP/1.0", "HTTP/1.1"):
                raise ValueError("Unsupported HTTP version")

            headers: dict[str, str] = {}
            for line in lines[1:]:
                if not line or ":" not in line:
                    raise ValueError("Malformed header")
                name, value = line.split(":", 1)
                name = name.strip().lower()
                if not name:
                    raise ValueError("Empty header name")
                headers[name] = value.strip()
        except ValueError as error:
            raise HTTPRequestError(400, str(error)) from error

        try:
            body_length = int(headers.get("content-length", "0"))
        except ValueError as error:
            raise HTTPRequestError(400, "Invalid Content-Length") from error
        if body_length < 0:
            raise HTTPRequestError(400, "Invalid Content-Length")
        if body_length > SETTINGS['MAX_HEADER_BYTES']:
            raise HTTPRequestError(413)
        while len(self._buffer) < body_length:
            chunk = self.client_socket.recv(min(4096, body_length - len(self._buffer)))
            if not chunk:
                raise HTTPRequestError(400, "Incomplete request body")
            self._buffer.extend(chunk)
        if body_length:
            del self._buffer[:body_length]

        return method.upper(), target, version, headers

    @staticmethod
    def _should_keep_alive(version: str, headers: dict[str, str]) -> bool:
        connection_header = headers.get("connection", "").lower()
        if "close" in {token.strip() for token in connection_header.split(",")}:
            return False
        if version == "HTTP/1.1":
            return True
        return "keep-alive" in {
            token.strip() for token in connection_header.split(",")
        }

    def _resolve_file(self, target: str) -> Path:
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            raise HTTPRequestError(400, "Expected origin-form request target")
        decoded_path = unquote(parsed.path)
        if "\x00" in decoded_path or "\\" in decoded_path:
            raise HTTPRequestError(404)
        relative_path = decoded_path.lstrip("/") or "me.html"
        file_path = (self.document_root / relative_path).resolve()
        if not file_path.is_relative_to(self.document_root):
            raise HTTPRequestError(404)
        if file_path.suffix.lower() not in SETTINGS['ALLOWED_EXTENSIONS']:
            raise HTTPRequestError(404)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        return file_path

    @staticmethod
    def _content_type(file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".html":
            return "text/html; charset=utf-8"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        return mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    def _send_response(
            self,
            status: int,
            body: bytes,
            content_type: str,
            keep_alive: bool,
            extra_headers: dict[str, str] | None = None,
    ) -> None:
        reason = STATUS_REASONS[status]
        connection_value = "keep-alive" if keep_alive else "close"
        headers = [
            f"HTTP/1.1 {status} {reason}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body)}",
            "Cache-Control: no-cache",
            f"Connection: {connection_value}",
        ]
        for name, value in (extra_headers or {}).items():
            headers.append(f"{name}: {value}")
        response_head = ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8")
        self.client_socket.sendall(response_head + body)

        log(f"-{self.connection_id}-Response: {len(body)} {content_type} {status} {reason}", 'light-cyan')
