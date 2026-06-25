import socket
import struct
import unittest

from digital_fruit_fly.bridge.messages import SCHEMA_VERSION, ErrorFrame, Hello
from digital_fruit_fly.bridge.transport import (
    FramedJsonSocket,
    TransportTimeoutError,
    TruncatedFrameError,
)


class TestFramedJsonTransport(unittest.TestCase):
    def test_loopback_round_trip_returns_typed_frame_when_message_is_complete(self) -> None:
        # Given: a connected local socket pair and a hello frame.
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        sender = FramedJsonSocket(left, timeout_s=0.25)
        receiver = FramedJsonSocket(right, timeout_s=0.25)
        frame = Hello(
            schema_version=SCHEMA_VERSION,
            run_id="run-loopback",
            frame_index=0,
            simulation_time_s=0.0,
            sent_monotonic_s=44.0,
            role="body",
        )

        # When: the sender writes one framed JSON message.
        sender.send_frame(frame)
        decoded = receiver.recv_frame()

        # Then: the receiver returns the typed frame.
        self.assertEqual(decoded, frame)

    def test_recv_frame_raises_timeout_when_peer_sends_nothing(self) -> None:
        # Given: a connected local socket pair with a short read timeout.
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        receiver = FramedJsonSocket(right, timeout_s=0.05)

        # When / Then: reading without a frame fails quickly and explicitly.
        with self.assertRaises(TransportTimeoutError):
            receiver.recv_frame()

    def test_recv_frame_raises_truncated_frame_when_peer_closes_mid_payload(self) -> None:
        # Given: a peer that advertises more bytes than it sends.
        left, right = socket.socketpair()
        self.addCleanup(right.close)
        receiver = FramedJsonSocket(right, timeout_s=0.25)
        left.sendall(struct.pack(">I", 12))
        left.sendall(b'{"type"')
        left.close()

        # When / Then: the receiver reports a truncated frame.
        with self.assertRaises(TruncatedFrameError):
            receiver.recv_frame()

    def test_future_schema_returns_error_frame_and_closes_receiver(self) -> None:
        # Given: a peer sends a frame with a future schema version.
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        receiver = FramedJsonSocket(right, timeout_s=0.25)
        future = (
            b'{"type":"hello","schema_version":999,"run_id":"run-future",'
            b'"frame_index":0,"simulation_time_s":0.0,'
            b'"sent_monotonic_s":1.0,"role":"brain"}'
        )
        left.sendall(struct.pack(">I", len(future)) + future)

        # When: the receiver decodes the frame.
        decoded = receiver.recv_frame()

        # Then: an error frame is returned and the local receiver is closed.
        self.assertIsInstance(decoded, ErrorFrame)
        self.assertEqual(decoded.code, "schema_version_unsupported")
        self.assertTrue(receiver.closed)


if __name__ == "__main__":
    unittest.main()
