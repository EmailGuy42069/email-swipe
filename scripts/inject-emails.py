#!/usr/bin/env python3
"""Write agent-fetched emails to the UI inbox file."""
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / 'assets' / 'ui' / 'emails.json'


def main():
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    emails = data if isinstance(data, list) else data.get('emails', [])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(emails, f, indent=2)

    print(f'Loaded {len(emails)} emails → {OUTPUT}')


if __name__ == '__main__':
    main()
