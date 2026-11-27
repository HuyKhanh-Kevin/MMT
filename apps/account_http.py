import argparse
import json
import socket
import threading
import time

from apps.account_sessions import AccountSessions
from apps.routes.account_http_routes import AccountHttpRoutes


class AccountHttpServer:
    def __init__(self, sessions, port=8081):
        self.routes = AccountHttpRoutes(sessions)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._clients = {}
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._socket.bind(("127.0.0.1", port))
            self._socket.listen(32)
            self._socket.settimeout(0.2)
        except BaseException:
            self._socket.close()
            raise
        self.port = self._socket.getsockname()[1]
        self._thread = threading.Thread(target=self._accept, name="account-http", daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _accept(self):
        while not self._stop.is_set():
            try:
                peer, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                if self._stop.is_set() or len(self._clients) >= 32:
                    peer.close()
                    continue
                worker = threading.Thread(target=self._serve, args=(peer,), daemon=True)
                self._clients[peer] = worker
                worker.start()

    def _read_more(self, peer, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP request timed out")
        peer.settimeout(remaining)
        chunk = peer.recv(4096)
        if not chunk:
            raise ValueError("Incomplete HTTP request")
        return chunk

    def _read_request(self, peer):

        deadline = time.monotonic() + 5
        data = bytearray()
        while b"\r\n\r\n" not in data:
            data.extend(self._read_more(peer, deadline))
            if len(data) > 10240:
                raise ValueError("Request too large")
        head, body = bytes(data).split(b"\r\n\r\n", 1)
        if len(head) > 8192:
            raise ValueError("Headers too large")
        lines = head.decode("ascii").split("\r\n")
        method, path, version = lines[0].split(" ")
        if version not in ("HTTP/1.0", "HTTP/1.1"):
            raise ValueError("Invalid HTTP version")
        headers = {}
        for line in lines[1:]:
            key, value = line.split(":", 1)
            if key == "" or not key.isascii():
                raise ValueError("Invalid header")
            for character in key:
                if not character.isalnum() and character != "-":
                    raise ValueError("Invalid header")
            key = key.lower()
            if key in headers:
                raise ValueError("Duplicate header")
            headers[key] = value.strip()
        if "transfer-encoding" in headers:
            raise ValueError("Chunked requests are not supported")
        size = headers.get("content-length", "0")
        if not size.isascii() or not size.isdecimal() or len(size) > 4 or int(size) > 2048:
            raise ValueError("Invalid content length")
        size = int(size)
        while len(body) < size:
            body += self._read_more(peer, deadline)
        if len(body) != size:
            raise ValueError("Pipelined/trailing data are not supported")
        return method, path, headers, body

    def _serve(self, peer):
        try:
            try:
                method, path, headers, body = self._read_request(peer)
                hosts = [f"127.0.0.1:{self.port}", f"localhost:{self.port}"]
                origins = []
                for host in hosts:
                    origins.append("http://" + host)
                if headers.get("host") not in hosts or (
                        "origin" in headers and headers["origin"] not in origins):
                    status, result = 403, {"status": "failed", "reason": "ORIGIN_NOT_ALLOWED"}
                elif method == "POST" and path in ("/login", "/signup") and (
                        headers.get("content-type", "").split(";")[0].strip() != "application/json"):
                    status, result = 415, {"status": "failed", "reason": "JSON_REQUIRED"}
                else:
                    status, result = self.routes.dispatch(method, path, headers, body)
            except (ValueError, UnicodeError, TimeoutError):
                status, result = 400, {"status": "failed", "reason": "INVALID_HTTP_REQUEST"}
            payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
            reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
                      404: "Not Found", 405: "Method Not Allowed", 409: "Conflict",
                      415: "Unsupported Media Type", 503: "Service Unavailable"}[status]
            header = (f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json; charset=utf-8\r\n"
                      f"Content-Length: {len(payload)}\r\nCache-Control: no-store\r\n"
                      "X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n")
            peer.settimeout(5)
            peer.sendall(header.encode("ascii") + payload)
        except OSError:
            pass
        finally:
            peer.close()
            with self._lock:
                self._clients.pop(peer, None)

    def close(self):
        self._stop.set()
        self._socket.close()
        with self._lock:
            clients = tuple(self._clients.items())
        for peer, _ in clients:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            peer.close()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        for _, worker in clients:
            worker.join(timeout=6)

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()


def main():
    parser = argparse.ArgumentParser(description="Local Python account HTTP API")
    parser.add_argument("--tracker", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=5000)
    parser.add_argument("--udp-port", type=int, default=5000)
    parser.add_argument("--http-port", type=int, default=8081)
    parser.add_argument("--peer-tcp-port", type=int, required=True)
    parser.add_argument("--file-udp-port", type=int, required=True)
    args = parser.parse_args()
    with AccountSessions(args.tracker, args.tcp_port, args.udp_port,
                         args.peer_tcp_port, args.file_udp_port) as sessions:
        with AccountHttpServer(sessions, args.http_port) as server:
            print(f"Account API: http://127.0.0.1:{server.port}", flush=True)
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
