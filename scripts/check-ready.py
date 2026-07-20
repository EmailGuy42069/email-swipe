#!/usr/bin/env python3
"""Readiness check for Email Swipe local use."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from pathlib import Path

from settings import USER_DIR

from agent_context import build_agent_context

ROOT = Path(__file__).resolve().parent.parent
DEMO_FILE = ROOT / 'assets' / 'ui' / 'demo-emails.json'
SERVER_FILE = ROOT / 'scripts' / 'serve-ui.py'
MCP_FILE = ROOT / 'scripts' / 'watch-preferences.py'


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('', port))
            return True
        except OSError:
            return False


def pick_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return int(s.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description='Check local readiness for Email Swipe')
    parser.add_argument('--json', action='store_true', help='Output JSON only')
    args = parser.parse_args()

    preferred_port = int(os.environ.get('PORT', '8765'))
    open_port = preferred_port if port_available(preferred_port) else pick_open_port()
    report = {
        'pythonVersion': sys.version.split()[0],
        'pythonOk': sys.version_info >= (3, 9),
        'preferredPort': preferred_port,
        'preferredPortAvailable': port_available(preferred_port),
        'suggestedPort': open_port,
        'configDirWritable': False,
        'demoEmailsPresent': DEMO_FILE.exists(),
        'serveUiPresent': SERVER_FILE.exists(),
        'mcpServerPresent': MCP_FILE.exists(),
        'gogAvailable': bool(shutil.which('gog')),
        'userDir': str(USER_DIR),
    }

    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        probe = USER_DIR / '.write-test'
        probe.write_text('ok\n', encoding='utf-8')
        probe.unlink(missing_ok=True)
        report['configDirWritable'] = True
    except OSError:
        report['configDirWritable'] = False

    report['ready'] = all([
        report['pythonOk'],
        report['configDirWritable'],
        report['demoEmailsPresent'],
        report['serveUiPresent'],
        report['mcpServerPresent'],
    ])
    report['agentContext'] = build_agent_context()

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report['ready'] else 1

    print('Email Swipe readiness')
    print(f"  Python:     {report['pythonVersion']} {'OK' if report['pythonOk'] else 'Needs 3.9+'}")
    print(f"  Config dir: {'writable' if report['configDirWritable'] else 'not writable'} ({USER_DIR})")
    print(f"  Demo mail:  {'present' if report['demoEmailsPresent'] else 'missing'}")
    print(f"  serve-ui:   {'present' if report['serveUiPresent'] else 'missing'}")
    print(f"  MCP:        {'present' if report['mcpServerPresent'] else 'missing'}")
    print(f"  Port:       preferred {preferred_port} {'free' if report['preferredPortAvailable'] else 'busy'}")
    print(f"  Suggested:  http://localhost:{report['suggestedPort']}")
    print(f"  gog CLI:    {'available' if report['gogAvailable'] else 'not found (only needed for direct mail fetch)'}")
    print('  Agent:      one UI — index.html at Desktop URL from serve-ui.py')
    print('              demo = sample mail, not demo.html; ignore gitignored runtime files')
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    sys.exit(main())
