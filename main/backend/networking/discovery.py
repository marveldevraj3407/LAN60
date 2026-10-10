"""UDP broadcast discovery daemon for peer detection and LAN username verification."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Callable, Dict, List, Optional

from backend.config import AppConfig
from backend.models import Peer
from backend.networking.protocol import (
    MSG_ANNOUNCE,
    MSG_GOODBYE,
    MSG_NAME_CHECK,
    MSG_NAME_TAKEN,
)

logger = logging.getLogger("Discovery")


class DiscoveryService:
    """Manages UDP broadcast announcement, peer registry, and name collision queries."""

    BROADCAST_INTERVAL = 3.0  # seconds between announcements
    PEER_TIMEOUT = 10.0  # seconds before peer is considered offline

    def __init__(
        self,
        config: AppConfig,
        on_peers_updated: Optional[Callable[[List[Peer]], None]] = None,
    ) -> None:
        self.config = config
        self.on_peers_updated = on_peers_updated

        self._peers: Dict[str, Peer] = {}  # device_id -> Peer
        self._lock = threading.Lock()
        self._running = False

        self._send_sock: Optional[socket.socket] = None
        self._recv_sock: Optional[socket.socket] = None

        self._broadcast_thread: Optional[threading.Thread] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._prune_thread: Optional[threading.Thread] = None

        # Name collision query synchronization
        self._pending_name_checks: Dict[str, threading.Event] = {}  # username -> Event
        self._taken_names: set[str] = set()

    def start(self) -> None:
        """Start discovery announcer, listener, and cleanup workers."""
        if self._running:
            return

        self._running = True

        # Setup UDP send socket
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Setup UDP receive socket
        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._recv_sock.bind(("", self.config.discovery_port))
        except Exception as e:
            logger.error(f"Failed to bind UDP discovery port {self.config.discovery_port}: {e}")

        # Start background threads
        self._listen_thread = threading.Thread(
            target=self._listen_loop, name="Discovery-Listener", daemon=True
        )
        self._broadcast_thread = threading.Thread(
            target=self._broadcast_loop, name="Discovery-Announcer", daemon=True
        )
        self._prune_thread = threading.Thread(
            target=self._prune_loop, name="Discovery-Pruner", daemon=True
        )

        self._listen_thread.start()
        self._broadcast_thread.start()
        self._prune_thread.start()
        logger.info(f"UDP Discovery started on port {self.config.discovery_port}")

    def stop(self) -> None:
        """Stop threads and announce departure."""
        if not self._running:
            return

        self._running = False
        self._send_goodbye()

        if self._recv_sock:
            try:
                self._recv_sock.close()
            except Exception:
                pass

        if self._send_sock:
            try:
                self._send_sock.close()
            except Exception:
                pass

        logger.info("UDP Discovery stopped")

    def _broadcast_packet(self, data: dict) -> None:
        """Broadcast discovery packet across all active network adapters and subnets."""
        try:
            msg_bytes = json.dumps(data).encode("utf-8")
        except Exception:
            return

        from backend.config import get_all_local_ips, get_broadcast_addresses

        all_ips = get_all_local_ips()

        # 1. First send via standard broadcast socket
        if self._send_sock:
            try:
                self._send_sock.sendto(msg_bytes, ("<broadcast>", self.config.discovery_port))
            except Exception:
                pass
            try:
                self._send_sock.sendto(msg_bytes, ("255.255.255.255", self.config.discovery_port))
            except Exception:
                pass

        # 2. Specifically bind to each network adapter (e.g. Wi-Fi, Ethernet) to force
        # Windows to emit packets out each physical card, bypassing virtual adapter priority
        for local_ip in all_ips:
            if local_ip.startswith("127."):
                continue
            try:
                adapter_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                adapter_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                try:
                    adapter_sock.bind((local_ip, 0))
                except Exception:
                    pass

                for target in get_broadcast_addresses(local_ip):
                    try:
                        adapter_sock.sendto(msg_bytes, (target, self.config.discovery_port))
                    except Exception:
                        pass
                adapter_sock.close()
            except Exception:
                pass

    def send_direct_announcement(self, target_ip: str, target_port: Optional[int] = None) -> None:
        """Send a direct unicast announcement to a specific IP address."""
        if not self.config.username:
            return
        port = target_port or self.config.discovery_port
        payload = {
            "type": MSG_ANNOUNCE,
            "device_id": self.config.device_id,
            "username": self.config.username,
            "hostname": self.config.hostname,
            "ip": self.config.local_ip,
            "tcp_port": self.config.transfer_port,
            "app_version": "2.0.0",
            "is_direct_reply": True,
        }
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(json.dumps(payload).encode("utf-8"), (target_ip, port))
            s.close()
            logger.info(f"Sent direct unicast discovery ping to {target_ip}:{port}")
        except Exception as e:
            logger.debug(f"Direct announcement to {target_ip} failed: {e}")

    def broadcast_presence(self) -> None:
        """Immediately broadcast an ANNOUNCE packet across all adapters."""
        if self.config.username:
            payload = {
                "type": MSG_ANNOUNCE,
                "device_id": self.config.device_id,
                "username": self.config.username,
                "hostname": self.config.hostname,
                "ip": self.config.local_ip,
                "tcp_port": self.config.transfer_port,
                "app_version": "2.0.0",
                "is_direct_reply": False,
            }
            self._broadcast_packet(payload)

    def register_peer(self, peer: Peer) -> None:
        """Explicitly register or update a peer (e.g. from an incoming TCP connection)."""
        if peer.device_id == self.config.device_id:
            return
        with self._lock:
            self._peers[peer.device_id] = peer
        self._notify_update()

    def _broadcast_loop(self) -> None:
        """Periodically broadcast ANNOUNCE message."""
        while self._running:
            # Only announce if a username has been set
            if self.config.username:
                payload = {
                    "type": MSG_ANNOUNCE,
                    "device_id": self.config.device_id,
                    "username": self.config.username,
                    "hostname": self.config.hostname,
                    "ip": self.config.local_ip,
                    "tcp_port": self.config.transfer_port,
                    "app_version": "2.0.0",
                    "is_direct_reply": False,
                }
                self._broadcast_packet(payload)
            time.sleep(self.BROADCAST_INTERVAL)

    def _send_goodbye(self) -> None:
        """Broadcast GOODBYE on shutdown."""
        payload = {
            "type": MSG_GOODBYE,
            "device_id": self.config.device_id,
            "username": self.config.username,
        }
        self._broadcast_packet(payload)

    def _listen_loop(self) -> None:
        """Listen for UDP discovery messages from other PCs."""
        while self._running and self._recv_sock:
            try:
                data, addr = self._recv_sock.recvfrom(4096)
                if not data:
                    continue
                packet = json.loads(data.decode("utf-8"))
                self._handle_incoming_packet(packet, addr[0])
            except (socket.error, OSError):
                break
            except Exception as e:
                logger.debug(f"Error handling discovery datagram: {e}")

    def _handle_incoming_packet(self, packet: dict, sender_ip: str) -> None:
        msg_type = packet.get("type")
        device_id = packet.get("device_id")

        # Ignore announcements from self
        if device_id == self.config.device_id:
            return

        if msg_type == MSG_ANNOUNCE and device_id:
            # Prefer the actual source IP that transmitted the UDP packet over the LAN
            if sender_ip and sender_ip != "127.0.0.1":
                resolved_ip = sender_ip
            else:
                resolved_ip = packet.get("ip") or sender_ip or "127.0.0.1"

            peer = Peer(
                device_id=device_id,
                username=packet.get("username", "Anonymous"),
                hostname=packet.get("hostname", "Unknown"),
                ip=resolved_ip,
                tcp_port=int(packet.get("tcp_port", self.config.transfer_port)),
                app_version=packet.get("app_version", "2.0.0"),
                last_seen=time.time(),
                is_online=True,
            )
            with self._lock:
                self._peers[device_id] = peer
            self._notify_update()

            # Bidirectional handshake: if this was a broadcast from another peer,
            # send a direct unicast back to the sender so they discover us immediately!
            if not packet.get("is_direct_reply", False) and self.config.username:
                self.send_direct_announcement(sender_ip, self.config.discovery_port)

        elif msg_type == MSG_GOODBYE and device_id:
            with self._lock:
                if device_id in self._peers:
                    self._peers[device_id].is_online = False
            self._notify_update()

        elif msg_type == MSG_NAME_CHECK:
            # Another PC is asking if this username is already in use
            requested_name = packet.get("requested_username", "").strip().lower()
            from_device = packet.get("from_device_id")
            if (
                from_device != self.config.device_id
                and self.config.username.strip().lower() == requested_name
            ):
                # We have this username! Broadcast NAME_TAKEN
                reply = {
                    "type": MSG_NAME_TAKEN,
                    "device_id": self.config.device_id,
                    "taken_username": self.config.username,
                }
                self._broadcast_packet(reply)

        elif msg_type == MSG_NAME_TAKEN:
            taken_name = packet.get("taken_username", "").strip().lower()
            self._taken_names.add(taken_name)
            if taken_name in self._pending_name_checks:
                self._pending_name_checks[taken_name].set()

    def check_username_availability(self, candidate_username: str, timeout_sec: float = 1.0) -> bool:
        """Check whether candidate_username is already used by an active LAN peer.

        Returns True if available, False if already taken.
        """
        clean_name = candidate_username.strip()
        if not clean_name:
            return False

        lower_name = clean_name.lower()

        # Check local peers registry first
        with self._lock:
            for p in self._peers.values():
                if p.is_online and p.username.strip().lower() == lower_name:
                    return False

        # Broadcast a query across LAN
        event = threading.Event()
        self._pending_name_checks[lower_name] = event
        if lower_name in self._taken_names:
            self._taken_names.remove(lower_name)

        query = {
            "type": MSG_NAME_CHECK,
            "requested_username": clean_name,
            "from_device_id": self.config.device_id,
        }
        self._broadcast_packet(query)

        # Wait up to timeout_sec for any collision responses
        event.wait(timeout=timeout_sec)
        self._pending_name_checks.pop(lower_name, None)

        return lower_name not in self._taken_names

    def _prune_once(self) -> bool:
        """Perform a single pass checking peer heartbeats. Returns True if any peer changed state."""
        now = time.time()
        state_changed = False
        with self._lock:
            for peer in self._peers.values():
                if peer.is_online and (now - peer.last_seen > self.PEER_TIMEOUT):
                    peer.is_online = False
                    state_changed = True

        if state_changed:
            self._notify_update()
        return state_changed

    def _prune_loop(self) -> None:
        """Periodically check peer heartbeats and mark inactive peers offline."""
        while self._running:
            self._prune_once()
            time.sleep(2.0)

    def _notify_update(self) -> None:
        """Notify registered UI or SSE callback."""
        if self.on_peers_updated:
            peers = self.get_peers()
            try:
                self.on_peers_updated(peers)
            except Exception as e:
                logger.debug(f"Peer update callback error: {e}")

    def get_peers(self) -> List[Peer]:
        """Return list of all registered peers."""
        with self._lock:
            return list(self._peers.values())

    def get_online_peers(self) -> List[Peer]:
        """Return list of currently active online peers."""
        with self._lock:
            return [p for p in self._peers.values() if p.is_online]
