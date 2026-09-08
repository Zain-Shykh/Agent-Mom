"""Message dataclass, JSON wire (de)serialization, and TCP length-prefix framing.

Wire schema (architecture.md §5):
{
  "type": "unicast | multicast | broadcast",
  "sender_id": "A1",
  "sender_addr": "127.0.0.1:6001",
  "timestamp": "2026-09-08T12:00:00Z",
  "encrypted": true,
  "payload": "<plaintext, or base64 AES-GCM ciphertext if encrypted=true>"
}
"""

import json
import socket
import struct
from dataclasses import asdict, dataclass

_FRAME_LEN_STRUCT = struct.Struct(">I")  # 4-byte big-endian length prefix


@dataclass
class Message:
    type: str
    sender_id: str
    sender_addr: str
    timestamp: str
    encrypted: bool
    payload: str

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self)).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        return cls(**json.loads(data.decode("utf-8")))


def pack_frame(data: bytes) -> bytes:
    """Prefix `data` with a 4-byte big-endian length, for TCP framing."""
    return _FRAME_LEN_STRUCT.pack(len(data)) + data


def read_frame(sock: socket.socket) -> bytes:
    """Read one length-prefixed frame from a TCP socket.

    Blocks until the full frame (length prefix + body) has been read.
    Raises ConnectionError if the peer closes before a full frame arrives.
    """
    header = _read_exact(sock, _FRAME_LEN_STRUCT.size)
    (length,) = _FRAME_LEN_STRUCT.unpack(header)
    return _read_exact(sock, length)


def _read_exact(sock: socket.socket, num_bytes: int) -> bytes:
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("socket closed before full frame was received")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
