"""TCP server for incoming transfer requests, interactive accept/reject, and 64 KB chunk receiving."""

from __future__ import annotations

import logging
from pathlib import Path
import socket
import threading
import time
from typing import Any, Dict, Optional

from backend.config import AppConfig
from backend.networking.protocol import (
    decode_packet_from_socket,
    encode_packet,
    MSG_CHUNK,
    MSG_CHUNK_ACK,
    MSG_TRANSFER_COMPLETE,
    MSG_TRANSFER_FAILED,
    MSG_TRANSFER_REQUEST,
    MSG_TRANSFER_RESPONSE,
    ProtocolError,
)
from backend.services.notification_service import NotificationBus
from backend.transfer.security import sanitize_filename

logger = logging.getLogger("TCPServer")


class TCPServer:
    """Listens for incoming TCP file transfer requests and receives streamed file chunks."""

    REQUEST_TIMEOUT_SEC = 60.0  # seconds to wait for receiver UI to Accept or Reject

    def __init__(
        self,
        config: AppConfig,
        notifier: NotificationBus,
        discovery: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.notifier = notifier
        self.discovery = discovery

        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._listen_thread: Optional[threading.Thread] = None

        # Pending user decisions for incoming requests: transfer_id -> (Event, result_dict)
        self._pending_decisions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        """Bind TCP socket and start listener loop."""
        if self._running:
            return

        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._server_sock.bind(("0.0.0.0", self.config.transfer_port))
            self._server_sock.listen(10)
            logger.info(f"TCP Transfer Server listening on port {self.config.transfer_port}")
        except Exception as e:
            logger.error(f"Failed to bind TCP server on port {self.config.transfer_port}: {e}")
            self._running = False
            return

        self._listen_thread = threading.Thread(
            target=self._accept_loop, name="TCPServer-Accept", daemon=True
        )
        self._listen_thread.start()

    def stop(self) -> None:
        """Shut down TCP server."""
        if not self._running:
            return

        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        logger.info("TCP Transfer Server stopped")

    def resolve_pending_request(self, transfer_id: str, accept: bool) -> bool:
        """Called by UI API when receiver clicks [ACCEPT] or [REJECT]."""
        with self._lock:
            pending = self._pending_decisions.get(transfer_id)
            if not pending:
                return False
            pending["accepted"] = accept
            pending["event"].set()
            return True

    def _accept_loop(self) -> None:
        """Accept incoming TCP connections and spawn worker threads."""
        while self._running and self._server_sock:
            try:
                client_sock, addr = self._server_sock.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    daemon=True,
                    name=f"TCPReceiver-{addr[0]}:{addr[1]}",
                )
                t.start()
            except (socket.error, OSError):
                break
            except Exception as e:
                logger.debug(f"Error accepting connection: {e}")

    def _handle_client(self, sock: socket.socket, addr: tuple) -> None:
        """Process an incoming transfer connection."""
        part_path: Optional[Path] = None
        transfer_id = ""

        try:
            sock.settimeout(20.0)
            req_header, _ = decode_packet_from_socket(sock)
            if req_header.get("type") != MSG_TRANSFER_REQUEST:
                raise ProtocolError(f"Expected TRANSFER_REQUEST, got {req_header.get('type')}")

            transfer_id = req_header.get("transfer_id", "")
            sender_info = req_header.get("sender", {})
            sender_username = sender_info.get("username", "Unknown")
            sender_hostname = sender_info.get("hostname", addr[0])
            sender_ip = sender_info.get("ip", addr[0])
            raw_item_name = req_header.get("item_name", "unnamed_file")
            clean_item_name = sanitize_filename(raw_item_name)
            total_bytes = req_header.get("total_bytes", 0)

            # Register decision event
            decision_event = threading.Event()
            decision_data = {"accepted": False, "event": decision_event}
            with self._lock:
                self._pending_decisions[transfer_id] = decision_data

            # Notify UI of incoming request modal
            self.notifier.publish("INCOMING_TRANSFER_REQUEST", {
                "transfer_id": transfer_id,
                "sender_username": sender_username,
                "sender_hostname": sender_hostname,
                "sender_ip": sender_ip,
                "item_name": clean_item_name,
                "total_bytes": total_bytes,
            })

            # Wait for user decision (Accept / Reject)
            approved = decision_event.wait(timeout=self.REQUEST_TIMEOUT_SEC)
            with self._lock:
                user_accepted = decision_data.get("accepted", False) if approved else False
                self._pending_decisions.pop(transfer_id, None)

            if not approved or not user_accepted:
                reason = "Transfer rejected by user" if approved else "Transfer request timed out"
                resp_packet = encode_packet({
                    "type": MSG_TRANSFER_RESPONSE,
                    "transfer_id": transfer_id,
                    "accepted": False,
                    "reason": reason,
                })
                sock.sendall(resp_packet)
                logger.info(f"Incoming transfer {transfer_id} rejected ({reason})")
                return

            # User accepted: send positive response
            resp_packet = encode_packet({
                "type": MSG_TRANSFER_RESPONSE,
                "transfer_id": transfer_id,
                "accepted": True,
            })
            sock.sendall(resp_packet)

            self.notifier.publish("TRANSFER_STARTED", {
                "transfer_id": transfer_id,
                "direction": "INCOMING",
                "item_name": clean_item_name,
                "peer_username": sender_username,
                "total_bytes": total_bytes,
            })

            # Prepare disk target in configured download folder
            dl_dir = self.config.download_dir.resolve()
            dl_dir.mkdir(parents=True, exist_ok=True)

            part_path = dl_dir / f"{clean_item_name}_{transfer_id}.part"
            target_path = dl_dir / clean_item_name

            # Collision avoidance if file already exists
            if target_path.exists():
                stem = target_path.stem
                suffix = target_path.suffix
                counter = 1
                while target_path.exists():
                    target_path = dl_dir / f"{stem} ({counter}){suffix}"
                    counter += 1

            transferred_bytes = 0
            stream_start = time.time()
            last_progress_emit = stream_start

            with open(part_path, "wb") as f_out:
                sock.settimeout(30.0)
                while True:
                    pkt_header, payload = decode_packet_from_socket(sock)
                    pkt_type = pkt_header.get("type")

                    if pkt_type == MSG_CHUNK:
                        f_out.write(payload)
                        transferred_bytes += len(payload)

                        # Acknowledge chunk
                        ack_pkt = encode_packet({
                            "type": MSG_CHUNK_ACK,
                            "transfer_id": transfer_id,
                            "chunk_index": pkt_header.get("chunk_index", 0),
                        })
                        sock.sendall(ack_pkt)

                        now = time.time()
                        if (now - last_progress_emit >= 0.2) or (transferred_bytes >= total_bytes):
                            last_progress_emit = now
                            elapsed = max(now - stream_start, 0.001)
                            speed_mbps = (transferred_bytes / (1024 * 1024)) / elapsed
                            percent = round((transferred_bytes / max(total_bytes, 1)) * 100, 1)

                            self.notifier.publish("TRANSFER_PROGRESS", {
                                "transfer_id": transfer_id,
                                "direction": "INCOMING",
                                "transferred_bytes": transferred_bytes,
                                "total_bytes": total_bytes,
                                "progress_percent": percent,
                                "speed_mbps": round(speed_mbps, 2),
                            })

                    elif pkt_type == MSG_TRANSFER_COMPLETE:
                        break
                    else:
                        raise ProtocolError(f"Unexpected packet in stream: {pkt_type}")

            # Finalize: rename .part to target filename
            if part_path and part_path.exists():
                if target_path.exists():
                    target_path.unlink()
                part_path.rename(target_path)

            # Send completion confirmation back to sender so sender knows disk assembly is finished
            done_ack = encode_packet({
                "type": MSG_TRANSFER_COMPLETE,
                "transfer_id": transfer_id,
            })
            sock.sendall(done_ack)

            elapsed = max(time.time() - stream_start, 0.001)
            avg_speed_mbps = (transferred_bytes / (1024 * 1024)) / elapsed

            logger.info(f"Incoming file '{clean_item_name}' fully received ({transferred_bytes} bytes in {elapsed:.2f}s)")
            self.notifier.publish("TRANSFER_COMPLETED", {
                "transfer_id": transfer_id,
                "direction": "INCOMING",
                "item_name": target_path.name,
                "total_bytes": transferred_bytes,
                "duration_seconds": round(elapsed, 2),
                "average_speed_mbps": round(avg_speed_mbps, 2),
                "saved_path": str(target_path),
            })

        except Exception as e:
            logger.error(f"Error handling incoming transfer {transfer_id}: {e}")
            if part_path and part_path.exists():
                try:
                    part_path.unlink()
                except Exception:
                    pass
            if transfer_id:
                self.notifier.publish("TRANSFER_FAILED", {
                    "transfer_id": transfer_id,
                    "direction": "INCOMING",
                    "error": str(e),
                })
        finally:
            try:
                sock.close()
            except Exception:
                pass
