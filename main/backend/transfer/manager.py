"""Transfer orchestrator managing active single-file sessions and peer delivery."""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import uuid
from typing import Any, Dict, List

from backend.config import AppConfig
from backend.models import Peer
from backend.networking.discovery import DiscoveryService
from backend.networking.tcp_client import TransferSender
from backend.networking.tcp_server import TCPServer
from backend.services.notification_service import NotificationBus
from backend.transfer.chunking import scan_source_item

logger = logging.getLogger("TransferManager")


class TransferManager:
    """Coordinates sending files, incoming accept/reject, and sender worker threads."""

    def __init__(
        self,
        config: AppConfig,
        notifier: NotificationBus,
        discovery: DiscoveryService,
        tcp_server: TCPServer,
    ) -> None:
        self.config = config
        self.notifier = notifier
        self.discovery = discovery
        self.tcp_server = tcp_server

        self._senders: Dict[str, TransferSender] = {}
        self._lock = threading.Lock()

    def send_to_recipients(
        self,
        source_path: str,
        recipient_device_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Initiate transfer of a source file to recipient peers."""
        path = Path(source_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Selected path does not exist: {source_path}")

        item_name, total_bytes = scan_source_item(path)
        logger.info(f"Initiating transfer of '{item_name}' ({total_bytes} bytes) to {len(recipient_device_ids)} recipient(s)")

        peers_map = {p.device_id: p for p in self.discovery.get_peers()}
        results = []

        for dev_id in recipient_device_ids:
            peer = peers_map.get(dev_id)
            if not peer:
                logger.warning(f"Recipient device {dev_id} not found in peer registry")
                continue

            transfer_id = f"tx_{uuid.uuid4().hex[:12]}"
            sender = TransferSender(
                config=self.config,
                notifier=self.notifier,
                transfer_id=transfer_id,
                peer=peer,
                source_path=path,
                item_name=item_name,
                total_bytes=total_bytes,
            )

            with self._lock:
                self._senders[transfer_id] = sender

            thread = threading.Thread(
                target=self._run_sender_thread,
                args=(transfer_id, sender),
                daemon=True,
                name=f"Sender-{transfer_id}",
            )
            thread.start()

            results.append({
                "transfer_id": transfer_id,
                "recipient_username": peer.username,
                "recipient_hostname": peer.hostname,
                "status": "PENDING",
            })

        return results

    def _run_sender_thread(self, transfer_id: str, sender: TransferSender) -> None:
        try:
            sender.run()
        finally:
            with self._lock:
                self._senders.pop(transfer_id, None)

    def accept_incoming(self, transfer_id: str) -> bool:
        """User accepted incoming transfer request."""
        return self.tcp_server.resolve_pending_request(transfer_id, accept=True)

    def reject_incoming(self, transfer_id: str) -> bool:
        """User rejected incoming transfer request."""
        return self.tcp_server.resolve_pending_request(transfer_id, accept=False)
