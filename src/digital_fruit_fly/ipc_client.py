"""脑 worker 的 TCP JSON-lines 客户端（一次请求一连接）。"""

from __future__ import annotations

import socket

from .messages import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)


class TcpJsonlClient:
    """极简的一请求一连接 TCP 客户端。"""

    def __init__(self, *, host: str, port: int, timeout_s: float = 600.0) -> None:
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)

    def request(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        """发送一条感觉消息并返回一条脑读出响应。"""
        with socket.create_connection(
            (self.host, self.port), timeout=self.timeout_s
        ) as sock:
            sock.settimeout(self.timeout_s)
            sock.sendall(encode_message(message))
            response = sock.makefile("rb").readline()
        decoded = decode_message(response)
        if not isinstance(decoded, BrainReadoutMessage):
            raise ValueError(f"期望 brain_readout 响应，却得到 {decoded!r}")
        return decoded
