"""脑/身体双进程的 TCP JSON-lines 传输（纯标准库）。

- ``JsonLineServer``：脑进程侧，阻塞式单连接单请求。收到 ``SensoryMessage`` → 交给
  注入的 ``handler`` → 回 ``MotorMessage``。
- ``JsonLineClient``：身体进程侧，``request(SensoryMessage) -> MotorMessage``，每请求一次
  短连接（与服务端的单连接单请求匹配，最简且健壮）。

选用 TCP JSON-lines 而非 ZeroMQ：零额外依赖（两 conda 环境均无需装 pyzmq），且已在前序实现中
验证可用。每 15ms 同步窗握手一次。
"""

from __future__ import annotations

import socket
import threading
from typing import Callable

from .messages import MotorMessage, SensoryMessage, decode, encode

Handler = Callable[[SensoryMessage], MotorMessage]


class JsonLineServer:
    """极简阻塞式 TCP JSON-lines 服务端：一连接处理一条请求。"""

    def __init__(self, *, host: str, port: int, handler: Handler) -> None:
        self.host = host
        self.port = port
        self.handler = handler
        self._sock: socket.socket | None = None
        self._stop = threading.Event()

    @property
    def bound_port(self) -> int:
        return int(self._sock.getsockname()[1]) if self._sock else self.port

    def serve_forever(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen()
            sock.settimeout(0.2)
            self._sock = sock
            while not self._stop.is_set():
                try:
                    conn, _ = sock.accept()
                except (TimeoutError, socket.timeout):
                    continue
                with conn:
                    raw = conn.makefile("rb").readline()
                    if not raw:
                        continue
                    request = decode(raw)
                    if not isinstance(request, SensoryMessage):
                        continue
                    response = self.handler(request)
                    try:
                        conn.sendall(encode(response))
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        continue

    def shutdown(self) -> None:
        self._stop.set()


class JsonLineClient:
    """身体侧客户端：每请求短连接，发一行收一行。"""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 8765, timeout_s: float = 600.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s

    def request(self, message: SensoryMessage) -> MotorMessage:
        with socket.create_connection((self.host, self.port), timeout=self.timeout_s) as conn:
            conn.sendall(encode(message))
            raw = conn.makefile("rb").readline()
        response = decode(raw)
        if not isinstance(response, MotorMessage):
            raise ValueError(f"期望 MotorMessage，收到 {type(response).__name__}")
        return response

    def wait_until_ready(self, timeout_s: float) -> bool:
        """轮询直到脑服务端端口可连接（建网可能需若干秒）。"""
        import time
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((self.host, self.port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.3)
        return False
