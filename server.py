from core.server import WebServer
from core.utils.logs import log

def main() -> None:
    server = WebServer()
    try:
        server.run()
    except KeyboardInterrupt:
        log("\nStopping server...", 'magenta')
        server.shutdown()


if __name__ == "__main__":
    main()


