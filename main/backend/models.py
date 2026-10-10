"""Core data models for peers, transfers, packets, and metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import time
from typing import Any, Dict, List, Optional


@dataclass
class Peer:
    """Represents a discovered PC node on the local network."""

    device_id: str
    username: str
    hostname: str
    ip: str
    tcp_port: int
    app_version: str = "2.0.0"
    last_seen: float = field(default_factory=time.time)
    is_online: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "username": self.username,
            "hostname": self.hostname,
            "ip": self.ip,
            "tcp_port": self.tcp_port,
            "app_version": self.app_version,
            "last_seen": self.last_seen,
            "is_online": self.is_online,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Peer:
        return cls(
            device_id=d["device_id"],
            username=d.get("username", "Anonymous"),
            hostname=d.get("hostname", "Unknown"),
            ip=d["ip"],
            tcp_port=int(d["tcp_port"]),
            app_version=d.get("app_version", "2.0.0"),
            last_seen=d.get("last_seen", time.time()),
            is_online=d.get("is_online", True),
        )


@dataclass
class FileItem:
    """Represents a single file within a transfer (supports multi-file/folder)."""

    relative_path: str  # e.g. "docs/report.pdf" or "photo.jpg"
    size: int
    sha256: str = ""


@dataclass
class TransferJob:
    """Represents an active or queued transfer."""

    id: str
    direction: str  # 'OUTGOING' or 'INCOMING'
    peer_device_id: str
    peer_username: str
    peer_hostname: str
    peer_ip: str
    peer_port: int
    name: str  # Name of file
    total_bytes: int
    status: str = "PENDING"  # PENDING, ACCEPTED, REJECTED, IN_PROGRESS, COMPLETED, FAILED
    transferred_bytes: int = 0
    speed_mbps: float = 0.0
    eta_seconds: int = 0
    error_message: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    source_path: str = ""  # Local path for sender
    target_path: str = ""  # Local path for receiver

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["progress_percent"] = (
            round((self.transferred_bytes / self.total_bytes) * 100, 1)
            if self.total_bytes > 0
            else 0.0
        )
        return d
