"""Forward Polarish-vended host MinIO (localhost:MINIO_API_PORT) to Compose MinIO.

Spark runs inside Docker; Polaris catalog storage advertises the host MinIO port
from .env (default 9002). This proxy lets Iceberg S3FileIO reach MinIO on minio:9000.
"""

from __future__ import annotations

import os
import socket
import sys
import threading

LISTEN_HOST = "127.0.0.1"
TARGET_HOST = os.environ.get("MINIO_INTERNAL_HOST", "minio")
TARGET_PORT = int(os.environ.get("MINIO_INTERNAL_PORT", "9000"))
LISTEN_PORT = int(os.environ.get("MINIO_API_PORT", "9002"))


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            src.shutdown(socket.SHUT_RD)
        except OSError:
            pass
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle(client: socket.socket) -> None:
    try:
        upstream = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
    except OSError:
        client.close()
        return
    t1 = threading.Thread(target=_pipe, args=(client, upstream), daemon=True)
    t2 = threading.Thread(target=_pipe, args=(upstream, client), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    client.close()
    upstream.close()


def main() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((LISTEN_HOST, LISTEN_PORT))
    except OSError as exc:
        print(
            f"Failed to bind MinIO proxy on {LISTEN_HOST}:{LISTEN_PORT}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    server.listen(64)
    print(
        f"MinIO proxy {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}",
        flush=True,
    )
    while True:
        client, _ = server.accept()
        threading.Thread(target=_handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
