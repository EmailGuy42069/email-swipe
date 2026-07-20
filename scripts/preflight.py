#!/usr/bin/env python3
"""Legacy pre-flight — prefer `python scripts/check-ready.py --json`."""
import json
import os
import socket
import sys
from pathlib import Path

from email_config import USER_CONFIG_FILE, config_status
from session_state import load_runtime
from settings import SETTINGS_FILE, settings_status

SKILL_ROOT = Path(__file__).resolve().parent.parent
EMAILS_FILE = SKILL_ROOT / 'assets' / 'ui' / 'emails.json'
DEMO_FILE = SKILL_ROOT / 'assets' / 'ui' / 'demo-emails.json'
PREFS_DIR = Path.home() / '.config' / 'email-swipe'
PREFS_FILE = PREFS_DIR / 'preferences.json'


def deployment_urls():
    runtime = load_runtime()
    if runtime.get('desktopUrl'):
        return runtime['desktopUrl'], runtime.get('lanUrl')
    port = os.environ.get('PORT', '<dynamic>')
    ip = local_ip()
    desktop = f'http://localhost:{port}'
    mobile = f'http://{ip}:{port}' if ip else None
    return desktop, mobile


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
    print('Note: prefer check-ready.py — this script is legacy.\n', file=sys.stderr)
    agent_inbox = load_json(EMAILS_FILE)
    demo_inbox = load_json(DEMO_FILE)

    print('=== Email Swipe — Session Preflight ===\n')

    status = config_status()
    if status['emailConfigured']:
        print(f"✓ Email account: {status['email']}")
    else:
        print('✗ No email account configured')
        print(f'  → Run: python scripts/setup-config.py')
        print(f'  → Or create {USER_CONFIG_FILE} with {{"email": "you@example.com"}}')
        if status.get('emailError'):
            print(f'  → {status["emailError"].splitlines()[0]}')

    if status['gogAvailable']:
        print(f"✓ gog CLI: {status['gogPath']}")
    elif status['serviceAccountFiles']:
        print(f"✓ Gmail API credentials: {status['serviceAccountFiles'][0]}")
    else:
        print('· No gog or Gmail API credentials detected (agent can still inject emails manually)')

    setting_status = settings_status()
    print('\n--- Settings ---')
    if setting_status.get('settingsFile'):
        print(f"✓ Settings: {setting_status['settingsFile']}")
    else:
        print('· No settings file yet (optional — Advanced settings or setup-settings.py)')
    print(f"  Agent review: {'on' if setting_status['agentEnabled'] else 'off'}")
    print(f"  Folder style: {setting_status['folderPreference']}")
    print(f"  Urgent folder: {setting_status['urgentFolder']}")
    if setting_status.get('hasUserContext'):
        print('  User context: provided')

    print()

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
    desktop, mobile = deployment_urls()
    print(f'  Desktop:  {desktop}')
    if mobile:
        print(f'  Mobile:   {mobile}')
    else:
        print('  Mobile:   (could not detect LAN IP — run serve-ui.py for runtime.json)')

    print('\n--- Start server ---')
    print('  python scripts/serve-ui.py')

    if not agent_inbox:
        sys.exit(1)


if __name__ == '__main__':
    main()
