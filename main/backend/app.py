"""Flask application entry point and REST/SSE API router for 60% scope."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from backend.config import AppConfig
from backend.networking.discovery import DiscoveryService
from backend.networking.tcp_server import TCPServer
from backend.services.device_service import DeviceService
from backend.services.notification_service import NotificationBus
from backend.services.user_service import UserService
from backend.transfer.manager import TransferManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("App")


def create_app(custom_app_data_dir: Optional[Path] = None) -> Flask:
    """Application factory initializing system services and in-scope routes."""
    base_dir = Path(__file__).resolve().parent.parent
    frontend_dir = base_dir / "frontend"

    app = Flask(
        __name__,
        template_folder=str(frontend_dir / "templates"),
        static_folder=str(frontend_dir / "static"),
    )

    # Core system singletons
    config = AppConfig(custom_app_data_dir=custom_app_data_dir)
    notifier = NotificationBus()

    discovery = DiscoveryService(
        config=config,
        on_peers_updated=lambda peers: notifier.publish("PEERS_UPDATED", [p.to_dict() for p in peers]),
    )
    tcp_server = TCPServer(
        config=config,
        notifier=notifier,
        discovery=discovery,
    )
    transfer_mgr = TransferManager(
        config=config,
        notifier=notifier,
        discovery=discovery,
        tcp_server=tcp_server,
    )

    user_service = UserService(config, discovery)
    device_service = DeviceService(config, discovery)

    # Start network daemons
    discovery.start()
    tcp_server.start()

    # Store handles in app context
    app.config_obj = config
    app.notifier_obj = notifier
    app.discovery_obj = discovery
    app.tcp_server_obj = tcp_server
    app.transfer_mgr_obj = transfer_mgr

    # --- HTML Route ---
    @app.route("/")
    def index():
        return render_template("index.html")

    # --- Real-Time SSE Stream ---
    @app.route("/api/events")
    def event_stream():
        client_queue = notifier.subscribe()
        return Response(
            notifier.sse_stream(client_queue),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # --- Device & User Profile APIs ---
    @app.route("/api/status", methods=["GET"])
    def get_status():
        return jsonify({
            "config": config.to_dict(),
            "device": device_service.get_device_info(),
        })

    @app.route("/api/user/setup", methods=["POST"])
    def setup_user():
        data = request.get_json() or {}
        candidate = data.get("username", "")
        skip_lan = app.config.get("TESTING", False)
        ok, msg = user_service.set_username(candidate, skip_lan_check=skip_lan)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400
        return jsonify({"success": True, "message": msg, "user": user_service.get_user_profile()})

    @app.route("/api/user/update", methods=["POST"])
    def update_user():
        data = request.get_json() or {}
        candidate = data.get("username", "")
        skip_lan = app.config.get("TESTING", False)
        ok, msg = user_service.set_username(candidate, skip_lan_check=skip_lan)
        if not ok:
            return jsonify({"success": False, "message": msg}), 400
        notifier.publish("USER_UPDATED", user_service.get_user_profile())
        return jsonify({"success": True, "message": msg, "user": user_service.get_user_profile()})

    # --- Discovery Operations ---
    @app.route("/api/peers", methods=["GET"])
    def get_peers():
        peers = discovery.get_peers()
        return jsonify({"peers": [p.to_dict() for p in peers]})

    @app.route("/api/peers/refresh", methods=["POST"])
    def refresh_peers():
        discovery.broadcast_presence()
        return jsonify({"success": True})

    @app.route("/api/peers/ping", methods=["POST"])
    def ping_peer():
        data = request.get_json() or {}
        target_ip = data.get("ip", "").strip()
        if not target_ip:
            return jsonify({"success": False, "message": "Target IP required"}), 400

        discovery.ping_direct_ip(target_ip)
        return jsonify({"success": True, "message": f"Ping sent to {target_ip}"})

    # --- Single File Native Selection Dialogs ---
    @app.route("/api/select_file", methods=["POST"])
    def select_file_dialog():
        """Launch Windows native file open dialog."""
        selected_file = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", 1)
            root.lift()
            root.focus_force()
            selected_file = filedialog.askopenfilename(
                title="Select File to Send over LAN"
            )
            root.destroy()
        except Exception as e:
            logger.debug(f"Native file dialog unavailable: {e}")

        if selected_file:
            path = Path(selected_file)
            return jsonify({
                "selected": True,
                "path": str(path.resolve()),
                "name": path.name,
                "size": path.stat().st_size if path.is_file() else 0,
            })
        return jsonify({"selected": False, "path": ""})

    @app.route("/api/select_path", methods=["POST"])
    def select_path_direct():
        """Select a file by direct local path string."""
        data = request.get_json() or {}
        raw = data.get("path", "").strip().strip('"').strip("'")
        if not raw:
            return jsonify({"selected": False, "message": "Path is empty."}), 400
        path = Path(raw)
        if not path.exists():
            return jsonify({"selected": False, "message": f"Path not found on disk: {raw}"}), 404
        if not path.is_file():
            return jsonify({"selected": False, "message": "Selected path must be a regular file."}), 400

        return jsonify({
            "selected": True,
            "path": str(path.resolve()),
            "name": path.name,
            "size": path.stat().st_size,
        })

    # --- Transfer Operations ---
    @app.route("/api/transfers/send", methods=["POST"])
    def initiate_transfer():
        data = request.get_json() or {}
        source_path = data.get("source_path", "").strip()
        recipients = data.get("recipients", [])

        if not source_path:
            return jsonify({"success": False, "message": "Source path is required."}), 400
        if not recipients:
            return jsonify({"success": False, "message": "Please select at least one recipient."}), 400

        try:
            dispatched = transfer_mgr.send_to_recipients(
                source_path=source_path,
                recipient_device_ids=recipients,
            )
            return jsonify({"success": True, "transfers": dispatched})
        except Exception as e:
            logger.error(f"Failed to initiate transfer: {e}")
            return jsonify({"success": False, "message": str(e)}), 400

    @app.route("/api/transfers/<transfer_id>/accept", methods=["POST"])
    def accept_transfer(transfer_id: str):
        ok = transfer_mgr.accept_incoming(transfer_id)
        return jsonify({"success": ok})

    @app.route("/api/transfers/<transfer_id>/reject", methods=["POST"])
    def reject_transfer(transfer_id: str):
        ok = transfer_mgr.reject_incoming(transfer_id)
        return jsonify({"success": ok})

    # --- Settings ---
    @app.route("/api/settings", methods=["GET", "POST"])
    def handle_settings():
        if request.method == "GET":
            return jsonify(config.to_dict())

        data = request.get_json() or {}
        new_dl_dir = data.get("download_dir")
        if new_dl_dir:
            try:
                config.set_download_dir(new_dl_dir)
            except Exception as e:
                return jsonify({"success": False, "message": f"Invalid download path: {e}"}), 400

        config.save()
        notifier.publish("SETTINGS_UPDATED", config.to_dict())
        return jsonify({"success": True, "settings": config.to_dict()})

    @app.route("/api/settings/choose_download_dir", methods=["POST"])
    def choose_download_dir_dialog():
        """Interactive folder chooser for download location."""
        selected_dir = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", 1)
            root.lift()
            root.focus_force()
            selected_dir = filedialog.askdirectory(
                title="Choose LAN File Sharing Download Directory"
            )
            root.destroy()
        except Exception as e:
            logger.debug(f"Dialog unavailable: {e}")

        if selected_dir:
            config.set_download_dir(selected_dir)
            notifier.publish("SETTINGS_UPDATED", config.to_dict())
            return jsonify({"selected": True, "download_dir": str(config.download_dir)})
        return jsonify({"selected": False, "download_dir": str(config.download_dir)})

    return app
