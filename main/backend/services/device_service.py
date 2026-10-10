"""Device status and hardware identity service."""

from __future__ import annotations

import platform
import socket
from typing import Dict

from backend.config import AppConfig
from backend.networking.discovery import DiscoveryService


class DeviceService:
    """Provides local machine information and network statistics."""

    def __init__(self, config: AppConfig, discovery: DiscoveryService) -> None:
        self.config = config
        self.discovery = discovery

    def get_device_info(self) -> Dict[str, str]:
        return {
            "device_id": self.config.device_id,
            "hostname": self.config.hostname,
            "os": f"{platform.system()} {platform.release()}",
            "local_ip": self.config.local_ip,
            "discovery_port": str(self.config.discovery_port),
            "transfer_port": str(self.config.transfer_port),
            "download_dir": str(self.config.download_dir),
        }
