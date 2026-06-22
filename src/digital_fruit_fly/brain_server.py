"""脑 worker 的 TCP JSON-lines 服务端与后端选择。"""

from __future__ import annotations

import json
import socket
import threading
from typing import Any

from .brain_backend import (
    BrainBackendUnavailable,
    BrainWorkerConfig,
    ShiuFullBackend,
)
from .messages import (
    SensoryStateMessage,
    decode_message,
    encode_message,
)


def select_backend(name: str, config: BrainWorkerConfig, *, engine: Any | None = None):
    """选择全 Shiu 后端；``auto`` 是别名而非兜底。"""
    if name not in {"auto", "shiu_full"}:
        raise ValueError(f"未知脑 worker 后端: {name}")
    return ShiuFullBackend(config, engine=engine)


class BrainWorkerServer:
    """极简阻塞式 TCP JSON-lines 服务端：一连接处理一条请求。"""

    def __init__(self, *, host: str, port: int, backend: Any) -> None:
        self.host = host
        self.port = port
        self.backend = backend
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def bound_port(self) -> int:
        if self._sock is None:
            return self.port
        return int(self._sock.getsockname()[1])

    def serve_forever(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen()
            sock.settimeout(0.1)
            self._sock = sock
            while not self._stop.is_set():
                try:
                    conn, _addr = sock.accept()
                except (TimeoutError, socket.timeout):
                    continue
                with conn:
                    raw = conn.makefile("rb").readline()
                    if not raw:
                        continue
                    request = decode_message(raw)
                    if not isinstance(request, SensoryStateMessage):
                        continue
                    response = self.backend.handle(request)
                    try:
                        conn.sendall(encode_message(response))
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        continue

    def serve_background(self) -> threading.Thread:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self._thread

    def shutdown(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                with socket.create_connection((self.host, self.bound_port), timeout=0.1):
                    pass
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def smoke_response(backend_name: str, config: BrainWorkerConfig) -> dict[str, Any]:
    """构建后端并对一条合成请求返回一次响应（用于冒烟检查）。"""
    backend = select_backend(backend_name, config)
    message = SensoryStateMessage(
        request_id=1,
        time_s=0.0,
        food_cue=1.0,
        turn_bias=0.0,
        dust_level=0.0,
        dust_threshold_reached=False,
        food_contact=True,
        food_distance_mm=0.5,
    )
    response = backend.handle(message)
    payload = json.loads(encode_message(response).decode("utf-8"))
    # 神经元活动向量可能很长，冒烟输出里只保留统计信息
    payload["neuron_activity"] = f"<{len(payload.get('neuron_activity', []))} ints>"
    return {
        "backend_name": backend.backend_name,
        "metadata": backend.metadata,
        "response": payload,
    }
