"""Entrypoint for running the Linux Ops Assistant GUI Dashboard."""

import sys
import argparse
from ops_assistant.gui.server import start_gui_server


def main():
    parser = argparse.ArgumentParser(description="AI-Powered Linux Operations Assistant — Web GUI Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP to bind GUI server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8888, help="Port to bind GUI server (default: 8888)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open default web browser")

    args = parser.parse_args()

    server, url = start_gui_server(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser
    )

    print(f"
[+] Dashboard live at: {url}")
    print("[+] Press Ctrl+C to stop the GUI server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("
[*] Stopping GUI server...")
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()