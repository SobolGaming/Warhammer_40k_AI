from __future__ import annotations

import argparse
from collections.abc import Sequence
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import sleep

from warhammer40k_core.adapters.http_transport import create_http_server
from warhammer40k_core.adapters.server import AdapterGameServer


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the authenticated reference HTTP/OpenAPI contract for conformance.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--shutdown-file", type=Path)
    args = parser.parse_args(argv)

    server = create_http_server(
        host=args.host,
        port=args.port,
        api=AdapterGameServer(),
    )
    print(
        f"Serving Phase 18M reference contract at http://{args.host}:{args.port}",
        flush=True,
    )
    if args.shutdown_file is not None:
        Thread(
            target=_shutdown_when_requested,
            args=(server, args.shutdown_file),
            daemon=True,
        ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _shutdown_when_requested(server: ThreadingHTTPServer, shutdown_file: Path) -> None:
    while not shutdown_file.exists():
        sleep(0.1)
    server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
