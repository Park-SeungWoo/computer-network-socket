from __future__ import annotations
import threading

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set["ClientConnection"] = set()
        self._next_id = 0
        self._lock = threading.Lock()

    def add(self, connection: "ClientConnection") -> None:
        with self._lock:
            connection.connection_id = self._next_id
            self._next_id += 1
            self._connections.add(connection)

    def discard(self, connection: "ClientConnection") -> None:
        with self._lock:
            self._connections.discard(connection)

    def close_all(self) -> None:
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            connection.close()


