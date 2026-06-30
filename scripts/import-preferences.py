#!/usr/bin/env python3
"""Save exported preferences.json to the standard agent config path."""
import json
import shutil
import sys
from pathlib import Path

PREFS_DIR = Path.home() / '.config' / 'email-swipe'
PREFS_FILE = PREFS_DIR / 'preferences.json'


def main():
    if len(sys.argv) < 2:
        print('Usage: import-preferences.py <path/to/preferences.json>')
        print(f'  Copies to {PREFS_FILE}')
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f'Error: file not found: {src}')
        sys.exit(1)

    with open(src) as f:
        data = json.load(f)

    PREFS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, PREFS_FILE)

    total = data.get('metadata', {}).get('totalSwipes', '?')
    print(f'Imported {total} swipes → {PREFS_FILE}')


if __name__ == '__main__':
    main()
