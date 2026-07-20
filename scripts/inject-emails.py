#!/usr/bin/env python3
"""Write agent-fetched emails to the UI inbox file."""
import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / 'assets' / 'ui' / 'emails.json'
SESSION_META = Path(__file__).resolve().parent.parent / 'assets' / 'ui' / 'session-metadata.json'


def main():
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    metadata = {}
    emails = data
    if isinstance(data, dict):
        emails = data.get('emails', [])
        metadata = data.get('metadata', {})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(emails, f, indent=2)

    if metadata:
        with open(SESSION_META, 'w') as f:
            json.dump(metadata, f, indent=2)
            f.write('\n')
        print(f'Session mode: {metadata.get("sessionMode", metadata.get("intakePath", "?"))}')
        account_id = metadata.get('accountId')
        if account_id:
            label = metadata.get('accountLabel') or account_id
            print(f'Mailbox: {label} ({account_id})')

    print(f'Loaded {len(emails)} emails → {OUTPUT}')


if __name__ == '__main__':
    main()
