import socket
import struct
from dataclasses import dataclass
from typing import Final

from digital_fruit_fly.bridge.messages import BridgeFrame, ErrorFrame, decode_message, encode_message


MAX_FRAME_BYTES: Final = 1_048_576
_LENGTH_PREFIX_BYTES: Final = 4


class TransportError(OSError):
    """Base error for framed JSON socket failures."""


class TransportTimeoutError(TransportError):
    """Raised when a peer does not send data before the configured timeout."""


class TruncatedFrameError(TransportError):
    """Raised when a peer closes before a complete frame arrives."""


class FrameTooLargeError(TransportError):
    """Raised when a frame length exceeds the configured limit."""


@dataclass
class FramedJsonSocket:
    sock: socket.socket
    timeout_s: float
    max_frame_bytes: int = MAX_FRAME_BYTES
    closed: bool = False

    def __post_init__(self) -> None:
        self.sock.settimeout(self.timeout_s)

    def send_frame(self, frame: BridgeFrame) -> None:
        payload = encode_message(frame)
        if len(payload) > self.max_frame_bytes:
            raise FrameTooLargeError("frame exceeds maximum size")
        self.sock.sendall(struct.pack(">I", len(payload)) + payload)

    def recv_frame(self) -> BridgeFrame:
        prefix = self._recv_exact(_LENGTH_PREFIX_BYTES)
        length = struct.unpack(">I", prefix)[0]
        if length > self.max_frame_bytes:
            self.close()
            raise FrameTooLargeError("frame exceeds maximum size")
        payload = self._recv_exact(length)
        frame = decode_message(payload)
        if isinstance(frame, ErrorFrame):
            self.close()
        return frame

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            return

    def _recv_exact(self, byte_count: int) -> bytes:
        chunks = []
        remaining = byte_count
        while remaining > 0:
            try:
                chunk = self.sock.recv(remaining)
            except socket.timeout as exc:
                raise TransportTimeoutError("timed out waiting for frame bytes") from exc
            if chunk == b"":
                self.close()
                raise TruncatedFrameError("peer closed before frame was complete")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
