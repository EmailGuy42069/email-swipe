#!/usr/bin/env python3
"""Fetch a folder/label snapshot for import-sorting (learn_from_folders input).

Uses gog CLI when available. Outputs JSON:
  { "folders": [ { "name", "role"?, "emails": [ { "from", "subject", "snippet?" } ] } ] }

Example:
  python scripts/fetch_folder_snapshot.py -o folders.json --per-folder 10
  python scripts/learn_from_folders.py folders.json --preview
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from email_config import ConfigError, get_email_account, get_gog_path, load_config

# Gmail system labels → roles for learn_from_folders inference
SYSTEM_FOLDERS = [
    {'name': 'Inbox', 'gmail_label': 'INBOX', 'role': 'keep'},
    {'name': 'Starred', 'gmail_label': 'STARRED', 'role': 'important'},
    {'name': 'Trash', 'gmail_label': 'TRASH', 'role': 'dont_keep'},
    {'name': 'Spam', 'gmail_label': 'SPAM', 'role': 'dont_keep'},
]

SKIP_LABELS = {
    'SENT', 'DRAFT', 'UNREAD', 'CHAT',
    'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS',
    'CATEGORY_UPDATES', 'CATEGORY_FORUMS',
}


def _run_gog(gog_path: str, account: str, args: list[str], timeout: int = 60) -> str | None:
    cmd = [gog_path, 'gmail', *args, '-a', account, '-j', '--results-only']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f'gog error: {exc}', file=sys.stderr)
        return None
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return None
    return result.stdout


def fetch_labels(gog_path: str, account: str) -> list[dict]:
    out = _run_gog(gog_path, account, ['labels', 'list'])
    if not out:
        return []
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else data.get('labels', [])
    except json.JSONDecodeError:
        return []


def fetch_messages_for_label(
    gog_path: str,
    account: str,
    label: str,
    limit: int,
) -> list[dict]:
    # Gmail search: label name for user labels; in:trash etc. for system
    search_map = {
        'INBOX': 'in:inbox',
        'STARRED': 'is:starred',
        'TRASH': 'in:trash',
        'SPAM': 'in:spam',
    }
    query = search_map.get(label, f'label:{label}')
    out = _run_gog(
        gog_path,
        account,
        ['messages', 'search', query, '--max', str(limit)],
        timeout=90,
    )
    if not out:
        return []
    try:
        messages = json.loads(out)
        if not isinstance(messages, list):
            messages = messages.get('messages', [])
    except json.JSONDecodeError:
        return []

    emails = []
    for msg in messages[:limit]:
        from_field = msg.get('from', '')
        sender = from_field
        if '<' in from_field:
            sender = from_field.split('<')[0].strip().strip('"')
        elif '@' in from_field:
            sender = from_field.split('@')[0]
        emails.append({
            'id': msg.get('id', ''),
            'from': from_field,
            'sender': sender or 'Unknown',
            'subject': msg.get('subject', '(no subject)'),
            'snippet': msg.get('snippet', ''),
            'date': msg.get('date', ''),
        })
    return emails


def build_snapshot(
    gog_path: str,
    account: str,
    per_folder: int = 10,
    include_system: bool = True,
    label_filter: list[str] | None = None,
) -> dict:
    folders: list[dict] = []

    if include_system:
        for spec in SYSTEM_FOLDERS:
            if label_filter and spec['name'] not in label_filter:
                continue
            emails = fetch_messages_for_label(gog_path, account, spec['gmail_label'], per_folder)
            if emails or spec['gmail_label'] in ('INBOX', 'TRASH'):
                folders.append({
                    'name': spec['name'],
                    'role': spec['role'],
                    'emails': emails,
                })

    labels = fetch_labels(gog_path, account)
    for label in labels:
        name = label.get('name', '')
        if not name or name in SKIP_LABELS or name.startswith('CATEGORY_'):
            continue
        if name in {s['gmail_label'] for s in SYSTEM_FOLDERS}:
            continue
        if label_filter and name not in label_filter:
            continue
        emails = fetch_messages_for_label(gog_path, account, name, per_folder)
        if not emails:
            continue
        folders.append({'name': name, 'emails': emails})

    return {'folders': folders, 'folderPreference': 'moderate'}


def main() -> int:
    parser = argparse.ArgumentParser(description='Fetch folder snapshot for import-sorting')
    parser.add_argument('-o', '--output', default='-', help='Output file (- for stdout)')
    parser.add_argument('--per-folder', type=int, default=10, help='Max emails per folder')
    parser.add_argument('--no-system', action='store_true', help='Skip Inbox/Starred/Trash/Spam')
    parser.add_argument('--labels', help='Comma-separated folder names to include only')
    parser.add_argument('--account', '-a', help='Email account (overrides config)')
    parser.add_argument('--list-only', action='store_true', help='List label names and exit')
    args = parser.parse_args()

    if args.account:
        os.environ['EMAIL_SWIPE_EMAIL'] = args.account

    cfg = load_config()
    gog_path = get_gog_path(cfg)
    if not gog_path:
        print('gog CLI not found. Set EMAIL_SWIPE_GOG_PATH or install gog.', file=sys.stderr)
        print('See references/email-access.md', file=sys.stderr)
        return 1

    try:
        account = get_email_account(cfg)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.list_only:
        labels = fetch_labels(gog_path, account)
        names = [l.get('name', '') for l in labels if l.get('name')]
        print(json.dumps({'account': account, 'labels': names}, indent=2))
        return 0

    label_filter = [s.strip() for s in args.labels.split(',')] if args.labels else None
    snapshot = build_snapshot(
        gog_path,
        account,
        per_folder=args.per_folder,
        include_system=not args.no_system,
        label_filter=label_filter,
    )

    text = json.dumps(snapshot, indent=2)
    if args.output == '-':
        print(text)
    else:
        Path(args.output).write_text(text + '\n', encoding='utf-8')
        print(f'Wrote {len(snapshot["folders"])} folders → {args.output}', file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())
