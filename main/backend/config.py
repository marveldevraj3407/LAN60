"""Dynamic configuration management for Smart LAN File Sharing System.

CRITICAL PORTABILITY RULES:
1. NEVER hardcode Windows usernames (e.g. Devraj) or absolute drive paths.
2. ALL application-generated state (config, databases, partial chunks) MUST live
   outside the project source repository in the OS standard user app data folder.
3. Automatically detects hostname and network interfaces at runtime.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import socket
import sys
import uuid
from typing import Any, Dict, Optional


def get_app_data_dir() -> Path:
    """Return the platform-appropriate application data directory.

    Windows: %LOCALAPPDATA%/SmartLANFileShare (e.g. C:\\Users\\<user>\\AppData\\Local\\SmartLANFileShare)
    Linux/macOS: ~/.smart_lan_share
    """
    if platform.system() == "Windows":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data)
        else:
            base_dir = Path.home() / "AppData" / "Local"
    else:
        base_dir = Path.home() / ".config"

    app_dir = base_dir / "SmartLANFileShare"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_default_download_dir() -> Path:
    """Return the user's standard Downloads folder dynamically."""
    downloads = Path.home() / "Downloads" / "LAN File Sharing"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def get_local_ip() -> str:
    """Detect the machine's primary local LAN IP address.

    Falls back to 127.0.0.1 if network interface is not connected.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send packets; triggers OS routing lookup
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_all_local_ips() -> list[str]:
    """Enumerate all active IPv4 addresses across all adapters (Wi-Fi, Ethernet, etc.)."""
    ips = set()
    primary = get_local_ip()
    if primary and not primary.startswith("127."):
        ips.add(primary)

    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ":" not in ip:
                ips.add(ip)
    except Exception:
        pass

    return list(ips) if ips else ["127.0.0.1"]


def get_broadcast_addresses(ip: str) -> list[str]:
    """Calculate directed broadcast addresses for an IP to bypass Windows adapter routing issues."""
    targets = ["<broadcast>", "255.255.255.255"]
    parts = ip.split(".")
    if len(parts) == 4:
        # Directed /24 subnet broadcast (e.g. 10.16.206.255)
        targets.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
        # Directed /16 subnet broadcast (e.g. 10.16.255.255)
        targets.append(f"{parts[0]}.{parts[1]}.255.255")
    # Return unique targets in order
    return list(dict.fromkeys(targets))


def get_pc_name() -> str:
    """Detect current PC hostname dynamically."""
    return socket.gethostname() or platform.node() or "Unknown-PC"


class AppConfig:
    """Manages persistent configuration saved in OS AppData."""

    DEFAULT_DISCOVERY_PORT = 50055
    DEFAULT_TRANSFER_PORT = 50056
    DEFAULT_WEB_PORT = 5000

    def __init__(self, custom_app_data_dir: Optional[Path] = None) -> None:
        self.app_data_dir = custom_app_data_dir or get_app_data_dir()
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.app_data_dir / "config.json"

        # In-memory settings
        self.device_id: str = ""
        self.username: str = ""
        self.download_dir: Path = get_default_download_dir()
        self.discovery_port: int = self.DEFAULT_DISCOVERY_PORT
        self.transfer_port: int = self.DEFAULT_TRANSFER_PORT
        self.web_port: int = self.DEFAULT_WEB_PORT

        self.load()

    def load(self) -> None:
        """Load configuration from disk or initialize defaults."""
        data: Dict[str, Any] = {}
        if self.config_path.is_file():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to read {self.config_path}: {e}\n")

        # Persistent Device ID - generated once per machine/installation
        self.device_id = data.get("device_id") or str(uuid.uuid4())

        # Username - empty string triggers first-time setup UI
        self.username = (data.get("username") or "").strip()

        # Download directory
        download_path_str = data.get("download_dir")
        if download_path_str:
            self.download_dir = Path(download_path_str)
        else:
            self.download_dir = get_default_download_dir()

        self.discovery_port = int(data.get("discovery_port", self.DEFAULT_DISCOVERY_PORT))
        self.transfer_port = int(data.get("transfer_port", self.DEFAULT_TRANSFER_PORT))
        self.web_port = int(data.get("web_port", self.DEFAULT_WEB_PORT))

        # Save to ensure device_id and default fields exist on disk
        self.save()

    def save(self) -> None:
        """Save configuration to JSON file in AppData."""
        # Ensure download directory actually exists
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        payload = {
            "device_id": self.device_id,
            "username": self.username,
            "download_dir": str(self.download_dir.resolve()),
            "discovery_port": self.discovery_port,
            "transfer_port": self.transfer_port,
            "web_port": self.web_port,
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def set_username(self, new_username: str) -> None:
        """Update and save the username."""
        self.username = new_username.strip()
        self.save()

    def set_download_dir(self, new_path: str | Path) -> None:
        """Update and validate the download directory."""
        target = Path(new_path)
        target.mkdir(parents=True, exist_ok=True)
        self.download_dir = target
        self.save()

    @property
    def hostname(self) -> str:
        return get_pc_name()

    @property
    def local_ip(self) -> str:
        return get_local_ip()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration for frontend consumption."""
        return {
            "device_id": self.device_id,
            "username": self.username,
            "hostname": self.hostname,
            "local_ip": self.local_ip,
            "download_dir": str(self.download_dir),
            "discovery_port": self.discovery_port,
            "transfer_port": self.transfer_port,
            "web_port": self.web_port,
            "has_configured_user": bool(self.username),
        }
