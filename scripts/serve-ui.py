#!/usr/bin/env python3
"""Serve the email-swipe UI locally (desktop + LAN for mobile)."""
import http.server
import socket
import socketserver
import os

PORT = 8765
DIRECTORY = os.path.join(os.path.dirname(__file__), '../assets/ui')


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, format, *args):
        pass  # quiet server


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


if __name__ == '__main__':
    ip = local_ip()
    print('Email Swipe UI')
    print(f'  Desktop:  http://localhost:{PORT}')
    if ip:
        print(f'  Mobile:   http://{ip}:{PORT}  (same Wi‑Fi)')
    print('Press Ctrl+C to stop.')
    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        httpd.serve_forever()
