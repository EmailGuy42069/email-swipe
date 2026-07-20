#!/usr/bin/env python3
"""Serve the email-swipe UI locally (desktop + LAN for mobile)."""
from __future__ import annotations

import http.server
import json
import os
import socket
import socketserver
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from agent_context import activation_summary_lines, build_agent_context  # noqa: E402
from compile_training import compile_training  # noqa: E402
from session_state import (  # noqa: E402
    build_session_status,
    clear_session_progress,
    load_session_progress,
    make_session_id,
    save_session_progress,
    update_runtime_status,
    write_runtime,
)
from settings import (  # noqa: E402
    USER_DIR,
    SETTINGS_FILE,
    build_settings_api_payload,
    update_settings,
)

DIRECTORY = SCRIPT_DIR.parent / 'assets' / 'ui'
PREFS_PATH = USER_DIR / 'preferences.json'
SESSION_STATUS_ROUTE = '/api/session-status'
SESSION_PROGRESS_ROUTE = '/api/session-progress'
SETTINGS_ROUTE = '/api/settings'

ARTIFACT_ROUTES = {
    '/api/training-pack': USER_DIR / 'training-pack.json',
    '/api/policy-brief': USER_DIR / 'assistant-brief.md',
    '/api/policy-graph': USER_DIR / 'policy-graph.json',
    '/api/calibration': USER_DIR / 'calibration.json',
}

PORT = None
SESSION_ID = None
DESKTOP_URL = None
LAN_URL = None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        if self.path.endswith(('.json', '.html', '.js', '.css', '.md')):
            self.send_header('Cache-Control', 'no-store, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        path = self.path.split('?')[0]
        if path in ('/api/preferences', SESSION_STATUS_ROUTE, SESSION_PROGRESS_ROUTE, SETTINGS_ROUTE, *ARTIFACT_ROUTES):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            return
        super().do_OPTIONS()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == SESSION_STATUS_ROUTE:
            body = json.dumps(build_session_status()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == SESSION_PROGRESS_ROUTE:
            body = json.dumps(load_session_progress(), indent=2).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == SETTINGS_ROUTE:
            payload = build_settings_api_payload()
            body = json.dumps(payload, indent=2).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ARTIFACT_ROUTES:
            artifact = ARTIFACT_ROUTES[path]
            if not artifact.exists():
                self.send_error(404, 'Artifact not found — finish a training session first')
                return
            if path == '/api/policy-brief':
                content_type = 'text/markdown; charset=utf-8'
                body = artifact.read_text(encoding='utf-8').encode('utf-8')
            else:
                content_type = 'application/json'
                body = artifact.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == SESSION_PROGRESS_ROUTE:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
                return
            if not isinstance(payload, dict):
                self.send_error(400, 'Expected JSON object')
                return
            if payload.get('clear'):
                result = clear_session_progress()
            else:
                result = save_session_progress(payload)
            encoded = json.dumps({'ok': True, 'progress': result}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path == SETTINGS_ROUTE:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
                return
            settings = payload.get('settings') if isinstance(payload, dict) else None
            if not isinstance(settings, dict):
                self.send_error(400, 'Expected JSON object with settings')
                return
            compile_after = bool(payload.get('compile')) if isinstance(payload, dict) else False
            try:
                result = update_settings(settings, compile_after=compile_after)
            except (OSError, ValueError) as exc:
                result = {'ok': False, 'error': str(exc)}
            status = 200 if result.get('ok') else 500
            encoded = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path == '/api/preferences':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
                return
            PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            PREFS_PATH.write_bytes(body)
            try:
                result = compile_training(PREFS_PATH, USER_DIR, save_settings_from_prefs=True, session_id=SESSION_ID)
            except Exception as exc:  # noqa: BLE001
                result = {'ok': False, 'error': str(exc)}
            if not result.get('ok'):
                update_runtime_status('compile_failed')
            self.send_response(200 if result.get('ok') else 500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            return
        self.send_error(404)

    def log_message(self, format, *args):
        pass


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def choose_port() -> int:
    env_port = os.environ.get('PORT')
    if env_port:
        return int(env_port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return int(s.getsockname()[1])


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    PORT = choose_port()
    SESSION_ID = make_session_id()
    ip = local_ip()
    DESKTOP_URL = f'http://localhost:{PORT}'
    LAN_URL = f'http://{ip}:{PORT}' if ip else None
    write_runtime(SESSION_ID, PORT, DESKTOP_URL, LAN_URL, status='in_progress')
    print('Email Swipe UI')
    for line in activation_summary_lines():
        print(f'  {line}')
    print(f'  Session:  {SESSION_ID}')
    print(f'  Desktop:  {DESKTOP_URL}  ← open this (index.html)')
    if ip:
        print(f'  Mobile:   {LAN_URL}  (same Wi‑Fi)')
    print(f'  Saves to: {PREFS_PATH}')
    print('            GET  /api/session-status, /api/settings, /api/policy-brief, /api/training-pack, /api/policy-graph, /api/calibration')
    print('            POST /api/settings, /api/preferences (auto-compile)')
    print('Press Ctrl+C to stop.')
    try:
        with ReusableTCPServer(('', PORT), Handler) as httpd:
            httpd.serve_forever()
    finally:
        update_runtime_status('idle')
