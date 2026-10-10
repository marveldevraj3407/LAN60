#!/usr/bin/env python3
"""Entry point for Smart LAN File Sharing System.

Usage:
    python run.py [--port 5000] [--no-browser]
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
import threading
import time
import webbrowser

from backend.app import create_app
from backend.config import get_local_ip, get_pc_name


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart LAN File Sharing System")
    parser.add_argument("--port", type=int, default=5000, help="Web dashboard port (default: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    parser.add_argument("--data-dir", type=str, default=None, help="Custom app data directory for multi-instance testing")
    args = parser.parse_args()

    hostname = get_pc_name()
    local_ip = get_local_ip()

    # Ensure Windows console encoding compatibility
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("=" * 65)
    print("      [*] LAN FILE SHARING SYSTEM (v1.2)")
    print("=" * 65)
    print(f"  [+] PC Hostname:  {hostname}")
    print(f"  [+] Local LAN IP: {local_ip}")
    print(f"  [+] Web UI:       http://localhost:{args.port}")
    print(f"  [+] LAN Access:   http://{local_ip}:{args.port}")
    print("=" * 65)
    print("  Zero-dependency peer-to-peer file sharing running.")
    print("  Press Ctrl+C to stop.")
    print("=" * 65)

    custom_dir = Path(args.data_dir) if args.data_dir else None
    app = create_app(custom_app_data_dir=custom_dir)

    if not args.no_browser:
        def open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(f"http://localhost:{args.port}")
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        # Run Flask server with threaded=True to serve concurrent requests & SSE
        app.run(host="0.0.0.0", port=args.port, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    finally:
        # Cleanup daemons
        try:
            app.discovery_obj.stop()
            app.tcp_server_obj.stop()
        except Exception:
            pass
        print("Goodbye!")


if __name__ == "__main__":
    main()
