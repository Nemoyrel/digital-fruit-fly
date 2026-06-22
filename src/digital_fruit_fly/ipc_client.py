"""TCP JSON-lines client for L4 brain worker requests."""

from __future__ import annotations

import socket

from .ipc_protocol import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)


class TcpJsonlClient:
    """Small one-request-per-connection TCP client."""

    def __init__(self, *, host: str, port: int, timeout_s: float = 600.0) -> None:
        self.host = host
        self.port = int(port)
        self.timeout_s = float(timeout_s)

    def request(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        """Send one sensory message and return one brain readout response."""
        with socket.create_connection(
            (self.host, self.port),
            timeout=self.timeout_s,
        ) as sock:
            sock.settimeout(self.timeout_s)
            sock.sendall(encode_message(message))
            response = sock.makefile("rb").readline()
        decoded = decode_message(response)
        if not isinstance(decoded, BrainReadoutMessage):
            raise ValueError(f"Expected brain_readout response, got {decoded!r}")
        return decoded
