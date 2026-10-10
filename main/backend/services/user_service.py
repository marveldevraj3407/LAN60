"""User identity service managing username persistence and LAN uniqueness."""

from __future__ import annotations

import logging
from typing import Tuple

from backend.config import AppConfig
from backend.networking.discovery import DiscoveryService

logger = logging.getLogger("UserService")


class UserService:
    """Handles username validation, persistence, and collision checks across LAN."""

    def __init__(self, config: AppConfig, discovery: DiscoveryService) -> None:
        self.config = config
        self.discovery = discovery

    def get_user_profile(self) -> dict:
        """Return the current user profile and device details."""
        return {
            "username": self.config.username,
            "device_id": self.config.device_id,
            "hostname": self.config.hostname,
            "local_ip": self.config.local_ip,
            "has_configured_user": bool(self.config.username),
        }

    def set_username(self, candidate_username: str, skip_lan_check: bool = False) -> Tuple[bool, str]:
        """Validate and update the username.

        Returns (success, message).
        """
        clean_name = candidate_username.strip()
        if not clean_name:
            return False, "Username cannot be empty."

        if len(clean_name) < 2 or len(clean_name) > 32:
            return False, "Username must be between 2 and 32 characters."

        # If user isn't changing their own name, return ok
        if self.config.username and self.config.username.lower() == clean_name.lower():
            return True, "Username unchanged."

        # Check LAN collision if discovery is active and not explicitly skipped
        if not skip_lan_check:
            available = self.discovery.check_username_availability(clean_name, timeout_sec=0.8)
            if not available:
                return False, f"Username '{clean_name}' is already taken on this LAN. Please choose another."

        self.config.set_username(clean_name)
        logger.info(f"Username successfully updated to: {clean_name}")
        return True, "Username saved successfully."
