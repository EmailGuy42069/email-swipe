#!/usr/bin/env python3
"""Legacy CLI — prefer compile_training.py for the default flow."""
import json
import subprocess
import sys
from pathlib import Path

from settings import USER_DIR, load_settings

PREFS_FILE = USER_DIR / 'preferences.json'
SCRIPT_DIR = Path(__file__).resolve().parent


def main():
    if len(sys.argv) < 2:
        print('Usage: export-preferences.py <swipe-export.json>', file=sys.stderr)
        print('', file=sys.stderr)
        print('LEGACY: Use the UI Export button or:', file=sys.stderr)
        print('  python scripts/compile_training.py <preferences.json> --save-settings', file=sys.stderr)
        sys.exit(1)

    print(
        'Warning: export-preferences.py is legacy. Prefer compile_training.py after UI export.',
        file=sys.stderr,
    )

    with open(sys.argv[1]) as f:
        swipe_data = json.load(f)

    if isinstance(swipe_data, list):
        preferences = {'metadata': {'version': '2.0'}, 'swipes': swipe_data, 'settings': load_settings()}
    else:
        preferences = swipe_data

    USER_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREFS_FILE, 'w') as f:
        json.dump(preferences, f, indent=2)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / 'compile_training.py'), str(PREFS_FILE), '--save-settings'],
    )
    total = len(preferences.get('swipes', []))
    if result.returncode == 0:
        print(f'Wrote {PREFS_FILE} ({total} swipes) + training artifacts')
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
