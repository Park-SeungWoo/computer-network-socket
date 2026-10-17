from __future__ import annotations

import socket
import threading
from pathlib import Path

from core.utils.constants import SETTINGS
from core.connections.manager import ConnectionManager
from core.connections.connection import ClientConnection
from core.utils.logs import log


class WebServer:
    def __init__(self, host: str = SETTINGS['HOST'], port: int = SETTINGS['PORT']) -> None:
        self.host = host
        self.port = port
        self.document_root = Path(__file__).resolve().parent.parent / Path('resources')
        self.connection_manager = ConnectionManager()
        self._stopping = threading.Event()
        self._server_socket: socket.socket | None = None

    def run(self) -> None:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # IPv4, TCP
        self._server_socket = server_socket
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(128)
        server_socket.settimeout(1.0)
        log(f"Serving {self.document_root} on http://{self.host}:{self.port}", 'yellow')

        try:
            while not self._stopping.is_set():
                try:
                    client_socket, client_address = server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stopping.is_set():
                        break
                    raise

                cli_name = f"{client_address[0]}:{client_address[1]}"
                connection = ClientConnection(
                    cli_name,
                    client_socket,
                    client_address,
                    self.connection_manager,
                    self.document_root,
                )
                self.connection_manager.add(connection)
                log(
                    f"-{connection.connection_id}-Create connection: {client_address[0]}:{client_address[1]}",
                    "light-green",
                )
                connection.start()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._stopping.is_set():
            return
        self._stopping.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
        self.connection_manager.close_all()
