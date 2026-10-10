"""Binary framing and protocol constants for TCP and UDP communication.

Wire format for TCP packets:
+-------------------+----------------------+------------------------+-------------------------+
| Magic (4 bytes)   | Header Len (4 bytes) | JSON Header (variable) | Binary Payload (bytes)  |
| b'SLFS'           | uint32 big-endian    | UTF-8 string           | Length specified in hdr |
+-------------------+----------------------+------------------------+-------------------------+
"""

from __future__ import annotations

import json
import struct
from typing import Any, Dict, Optional, Tuple

MAGIC = b"SLFS"
MAGIC_LEN = 4
HEADER_PREFIX_FORMAT = "!4sI"  # 4 bytes magic + 4 bytes unsigned int
HEADER_PREFIX_LEN = struct.calcsize(HEADER_PREFIX_FORMAT)

# Message Types
MSG_ANNOUNCE = "ANNOUNCE"
MSG_GOODBYE = "GOODBYE"
MSG_NAME_CHECK = "NAME_CHECK"
MSG_NAME_TAKEN = "NAME_TAKEN"

MSG_TRANSFER_REQUEST = "TRANSFER_REQUEST"
MSG_TRANSFER_RESPONSE = "TRANSFER_RESPONSE"
MSG_CHUNK = "CHUNK"
MSG_CHUNK_ACK = "CHUNK_ACK"
MSG_TRANSFER_COMPLETE = "TRANSFER_COMPLETE"
MSG_TRANSFER_FAILED = "TRANSFER_FAILED"


class ProtocolError(Exception):
    """Raised when incoming packet violates the protocol specification."""
    pass


def encode_packet(header: Dict[str, Any], payload: bytes = b"") -> bytes:
    """Encode a dictionary header and optional binary payload into a framed packet."""
    header["payload_len"] = len(payload)
    header_json_bytes = json.dumps(header).encode("utf-8")
    prefix = struct.pack(HEADER_PREFIX_FORMAT, MAGIC, len(header_json_bytes))
    return prefix + header_json_bytes + payload


def read_exact(sock_recv_fn, num_bytes: int) -> bytes:
    """Read exactly num_bytes from a socket receiving function. Raises EOFError on socket close."""
    buf = bytearray(num_bytes)
    view = memoryview(buf)
    pos = 0
    while pos < num_bytes:
        to_read = min(num_bytes - pos, 262144)
        chunk = sock_recv_fn(to_read)
        if not chunk:
            raise EOFError("Socket closed prematurely while reading")
        n = len(chunk)
        view[pos : pos + n] = chunk
        pos += n
    return bytes(buf)


def decode_packet_from_socket(sock) -> Tuple[Dict[str, Any], bytes]:
    """Read and decode a framed packet directly from a TCP socket."""
    prefix_bytes = read_exact(sock.recv, HEADER_PREFIX_LEN)
    magic, header_len = struct.unpack(HEADER_PREFIX_FORMAT, prefix_bytes)

    if magic != MAGIC:
        raise ProtocolError(f"Invalid magic bytes: expected {MAGIC!r}, got {magic!r}")

    if header_len > 10 * 1024 * 1024:  # 10 MB sanity limit on header JSON
        raise ProtocolError(f"Header too large: {header_len} bytes")

    header_json_bytes = read_exact(sock.recv, header_len)
    try:
        header = json.loads(header_json_bytes.decode("utf-8"))
    except Exception as e:
        raise ProtocolError(f"Malformed JSON in header: {e}")

    payload_len = header.get("payload_len", 0)
    payload = b""
    if payload_len > 0:
        if hasattr(sock, "recv_into"):
            buf = bytearray(payload_len)
            view = memoryview(buf)
            pos = 0
            while pos < payload_len:
                n = sock.recv_into(view[pos:])
                if n == 0:
                    raise EOFError("Socket closed prematurely while reading")
                pos += n
            payload = bytes(buf)
        else:
            payload = read_exact(sock.recv, payload_len)

    return header, payload
