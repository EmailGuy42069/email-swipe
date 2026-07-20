#!/usr/bin/env python3
"""Import exported preferences.json and compile via compile_training.py (advanced CLI)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

PREFS_DIR = Path.home() / '.config' / 'email-swipe'
PREFS_FILE = PREFS_DIR / 'preferences.json'
SCRIPT_DIR = Path(__file__).resolve().parent


def main():
    if len(sys.argv) < 2:
        print('Usage: import-preferences.py <path/to/preferences.json> [--save-settings]')
        print(f'  Copies to {PREFS_FILE} and compiles all training artifacts')
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

    if data.get('settings'):
        print('Settings found in export — will merge during analysis.')

    cmd = [sys.executable, str(SCRIPT_DIR / 'compile_training.py'), str(PREFS_FILE)]
    if '--save-settings' in sys.argv:
        cmd.append('--save-settings')

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
