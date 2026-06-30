#!/usr/bin/env python3
"""Pre-flight checks before an email-swipe training session."""
import json
import socket
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
EMAILS_FILE = SKILL_ROOT / 'assets' / 'ui' / 'emails.json'
DEMO_FILE = SKILL_ROOT / 'assets' / 'ui' / 'demo-emails.json'
PREFS_DIR = Path.home() / '.config' / 'email-swipe'
PREFS_FILE = PREFS_DIR / 'preferences.json'
PORT = 8765


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def load_json(path):
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get('emails', [])


def main():
    agent_inbox = load_json(EMAILS_FILE)
    demo_inbox = load_json(DEMO_FILE)
    ip = local_ip()

    print('=== Email Swipe — Session Preflight ===\n')

    if agent_inbox:
        print(f'✓ Inbox ready: {len(agent_inbox)} emails in emails.json')
    else:
        print('✗ No agent inbox (emails.json is empty)')
        print(f'  → Fetch emails from the user\'s mail, then run:')
        print(f'    python scripts/inject-emails.py <batch.json>')
        print(f'  → Demo fallback available: {len(demo_inbox)} sample emails')

    if PREFS_FILE.exists():
        with open(PREFS_FILE) as f:
            prefs = json.load(f)
        total = prefs.get('metadata', {}).get('totalSwipes', '?')
        print(f'\n✓ Existing preferences: {PREFS_FILE} ({total} prior swipes)')
    else:
        print(f'\n· No saved preferences yet (will create after export)')

    print('\n--- Deployment URLs ---')
    print(f'  Desktop:  http://localhost:{PORT}')
    if ip:
        print(f'  Mobile:   http://{ip}:{PORT}')
    else:
        print('  Mobile:   (could not detect LAN IP)')

    print('\n--- Start server ---')
    print('  python scripts/serve-ui.py')

    if not agent_inbox:
        sys.exit(1)


if __name__ == '__main__':
    main()
