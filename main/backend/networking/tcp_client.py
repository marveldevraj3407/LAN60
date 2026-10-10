"""TCP client for initiating single-file transfers to peer PCs using 64 KB streaming."""

from __future__ import annotations

import logging
from pathlib import Path
import socket
import time
from typing import Optional

from backend.config import AppConfig
from backend.models import Peer
from backend.networking.protocol import (
    decode_packet_from_socket,
    encode_packet,
    MSG_CHUNK,
    MSG_CHUNK_ACK,
    MSG_TRANSFER_COMPLETE,
    MSG_TRANSFER_REQUEST,
    MSG_TRANSFER_RESPONSE,
    ProtocolError,
)
from backend.services.notification_service import NotificationBus
from backend.transfer.chunking import CHUNK_SIZE_64KB, stream_file_chunks

logger = logging.getLogger("TCPClient")


class TransferSender:
    """Handles an outgoing single-file transfer session to a recipient peer."""

    def __init__(
        self,
        config: AppConfig,
        notifier: NotificationBus,
        transfer_id: str,
        peer: Peer,
        source_path: Path | str,
        item_name: str,
        total_bytes: int,
    ) -> None:
        self.config = config
        self.notifier = notifier
        self.transfer_id = transfer_id
        self.peer = peer
        self.source_path = Path(source_path)
        self.item_name = item_name
        self.total_bytes = total_bytes

    def run(self) -> bool:
        """Execute the transfer session. Returns True on success, False on error/reject."""
        sock: Optional[socket.socket] = None
        transferred_bytes = 0

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(15.0)
            logger.info(f"Connecting to {self.peer.username} ({self.peer.ip}:{self.peer.tcp_port})")
            sock.connect((self.peer.ip, self.peer.tcp_port))

            # Step 1: Send TRANSFER_REQUEST
            req_packet = encode_packet({
                "type": MSG_TRANSFER_REQUEST,
                "transfer_id": self.transfer_id,
                "sender": {
                    "device_id": self.config.device_id,
                    "username": self.config.username,
                    "hostname": self.config.hostname,
                    "ip": self.config.local_ip,
                    "tcp_port": self.config.transfer_port,
                },
                "item_name": self.item_name,
                "total_bytes": self.total_bytes,
            })
            sock.sendall(req_packet)

            # Step 2: Wait for TRANSFER_RESPONSE (Accept or Reject)
            sock.settimeout(65.0)
            resp_header, _ = decode_packet_from_socket(sock)
            if resp_header.get("type") != MSG_TRANSFER_RESPONSE:
                raise ProtocolError(f"Expected TRANSFER_RESPONSE, got {resp_header.get('type')}")

            if not resp_header.get("accepted"):
                reason = resp_header.get("reason", "Rejected by recipient")
                logger.info(f"Transfer {self.transfer_id} rejected: {reason}")
                self.notifier.publish("TRANSFER_REJECTED", {
                    "transfer_id": self.transfer_id,
                    "peer_username": self.peer.username,
                    "reason": reason,
                })
                return False

            self.notifier.publish("TRANSFER_STARTED", {
                "transfer_id": self.transfer_id,
                "direction": "OUTGOING",
                "item_name": self.item_name,
                "peer_username": self.peer.username,
                "total_bytes": self.total_bytes,
            })

            sock.settimeout(30.0)
            stream_start_time = time.time()
            last_progress_emit = stream_start_time

            # Step 3: Stream 64 KB chunks directly from source file
            for chunk_index, offset, chunk_data in stream_file_chunks(self.source_path, chunk_size=CHUNK_SIZE_64KB):
                chunk_header = {
                    "type": MSG_CHUNK,
                    "transfer_id": self.transfer_id,
                    "chunk_index": chunk_index,
                    "offset": offset,
                }
                packet_bytes = encode_packet(chunk_header, chunk_data)
                sock.sendall(packet_bytes)

                # Wait for CHUNK_ACK
                ack_header, _ = decode_packet_from_socket(sock)
                if ack_header.get("type") != MSG_CHUNK_ACK:
                    raise ProtocolError(f"Expected CHUNK_ACK, got {ack_header.get('type')}")

                transferred_bytes += len(chunk_data)

                # Periodic progress notification (every 0.2s or upon completion)
                now = time.time()
                if (now - last_progress_emit >= 0.2) or (transferred_bytes >= self.total_bytes):
                    last_progress_emit = now
                    elapsed = max(now - stream_start_time, 0.001)
                    speed_mbps = (transferred_bytes / (1024 * 1024)) / elapsed
                    percent = round((transferred_bytes / max(self.total_bytes, 1)) * 100, 1)

                    self.notifier.publish("TRANSFER_PROGRESS", {
                        "transfer_id": self.transfer_id,
                        "direction": "OUTGOING",
                        "transferred_bytes": transferred_bytes,
                        "total_bytes": self.total_bytes,
                        "progress_percent": percent,
                        "speed_mbps": round(speed_mbps, 2),
                    })

            # Step 4: Send TRANSFER_COMPLETE and wait for server to finalize disk reassembly
            complete_packet = encode_packet({
                "type": MSG_TRANSFER_COMPLETE,
                "transfer_id": self.transfer_id,
            })
            sock.sendall(complete_packet)

            conf_header, _ = decode_packet_from_socket(sock)
            if conf_header.get("type") != MSG_TRANSFER_COMPLETE:
                raise ProtocolError(f"Expected TRANSFER_COMPLETE confirmation, got {conf_header.get('type')}")

            elapsed = max(time.time() - stream_start_time, 0.001)
            avg_speed_mbps = (transferred_bytes / (1024 * 1024)) / elapsed

            logger.info(f"Transfer {self.transfer_id} completed: {transferred_bytes} bytes in {elapsed:.2f}s ({avg_speed_mbps:.2f} MB/s)")
            self.notifier.publish("TRANSFER_COMPLETED", {
                "transfer_id": self.transfer_id,
                "direction": "OUTGOING",
                "item_name": self.item_name,
                "total_bytes": self.total_bytes,
                "duration_seconds": round(elapsed, 2),
                "average_speed_mbps": round(avg_speed_mbps, 2),
            })
            return True

        except Exception as e:
            logger.error(f"Transfer {self.transfer_id} failed: {e}")
            self.notifier.publish("TRANSFER_FAILED", {
                "transfer_id": self.transfer_id,
                "direction": "OUTGOING",
                "item_name": self.item_name,
                "error": str(e),
            })
            return False

        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
