#!/usr/bin/env python3
"""Learn routing rules from a user's EXISTING folder sorting — no swipe UI.

For users who say "my inbox is already sorted, just learn from it." Reads a
snapshot of the user's folders and the mail already filed in each, infers
training signals + folder routes, then runs the normal compile pipeline so the
agent gets the same artifacts (policy-graph, platform-rules, brief) it would from
a swipe session.

Input JSON (path arg or stdin):
{
  "folders": [
    {"name": "Receipts", "role": "file", "emails": [{"from": "billing@shop.com", "subject": "..."}]},
    {"name": "Trash",    "role": "dont_keep", "emails": [...]},
    {"name": "Inbox",    "role": "keep",      "emails": [...]}
  ],
  "folderPreference": "moderate"   // optional: minimal | moderate | many
}

role is optional; inferred from the folder name when omitted:
  keep | important | dont_keep | file

Use --preview to print the plan (what rules would be created) WITHOUT writing
anything — use this to confirm with the user before committing, since their
preferences may have changed or a folder may hold stale/lingering mail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from compile_training import compile_training
from folder_intent import INTENT_DEFINITIONS  # noqa: F401  (kept for parity/validation)
from settings import USER_DIR

PREFS_FILE = USER_DIR / 'preferences.json'

DONT_KEEP_NAMES = ('trash', 'deleted', 'bin', 'spam', 'junk')
IMPORTANT_NAMES = ('important', 'starred', 'flagged', 'priority', 'vip')
KEEP_NAMES = ('inbox', 'keep', 'archive', 'all mail', 'saved')

# Folder-name hints → built-in smart categories (folder_intent intents).
INTENT_NAME_HINTS = {
    'receipts': ('receipt', 'order', 'purchase', 'invoice', 'payment', 'billing'),
    'newsletters': ('newsletter', 'digest', 'substack', 'reading', 'subscriptions'),
    'promotions': ('promo', 'deal', 'offer', 'marketing', 'sale', 'shopping', 'coupon'),
    'social': ('social', 'linkedin', 'facebook', 'twitter', 'instagram', 'network'),
    'notifications': ('notification', 'alert', 'update', 'system'),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_role(name: str, explicit: str | None = None) -> str:
    if explicit in ('keep', 'important', 'dont_keep', 'file'):
        return explicit
    low = name.lower().strip()
    if any(k in low for k in DONT_KEEP_NAMES):
        return 'dont_keep'
    if any(k in low for k in IMPORTANT_NAMES):
        return 'important'
    if any(low == k or f' {k}' in f' {low}' for k in KEEP_NAMES):
        return 'keep'
    return 'file'


def domain_of(addr: str) -> str:
    addr = (addr or '').lower()
    if '@' in addr:
        return addr.split('@', 1)[1].strip('> ')
    return ''


def map_intent(name: str) -> str | None:
    low = name.lower()
    for intent, hints in INTENT_NAME_HINTS.items():
        if any(h in low for h in hints):
            return intent
    return None


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')[:40] or 'x'


def _swipe(idx: int, email: dict, action: str, folder_route: dict | None = None) -> dict:
    frm = email.get('from') or email.get('sender') or ''
    sender = email.get('sender') or (frm.split('@')[0] if '@' in frm else frm) or 'Unknown'
    swipe = {
        'emailId': email.get('id', f'folder-{idx}'),
        'action': action,
        'sender': sender,
        'from': frm,
        'subject': email.get('subject', ''),
        'snippet': email.get('snippet') or email.get('body', ''),
        'source': 'folder-sorting',
        'timestamp': _now(),
    }
    if folder_route:
        swipe['folderRoute'] = folder_route
    return swipe


ACTION_BY_ROLE = {'keep': 'keep', 'important': 'important', 'dont_keep': 'spam'}


def build_plan(folders: list[dict], folder_preference: str = 'moderate') -> dict:
    """Turn folder snapshot into swipes + settings.routes + a human-readable plan."""
    swipes: list[dict] = []
    routes: list[dict] = [
        {'id': 'route-dont-keep', 'name': "Don't Keep", 'action': 'spam'},
        {'id': 'route-important', 'name': 'Important', 'action': 'important'},
        {'id': 'route-keep', 'name': 'Keep', 'action': 'keep'},
    ]
    plan: list[dict] = []
    idx = 0

    for folder in folders:
        name = (folder.get('name') or '').strip()
        if not name:
            continue
        emails = folder.get('emails') or []
        role = infer_role(name, folder.get('role'))
        entry = {'folder': name, 'role': role, 'emailCount': len(emails), 'rules': []}

        if role in ACTION_BY_ROLE:
            action = ACTION_BY_ROLE[role]
            for email in emails:
                idx += 1
                swipes.append(_swipe(idx, email, action))
            entry['rules'].append(f'{len(emails)} emails → training action "{action}"')
            plan.append(entry)
            continue

        # role == 'file' → folder route
        domains = Counter(
            domain_of(e.get('from') or e.get('sender')) for e in emails
            if domain_of(e.get('from') or e.get('sender'))
        )
        top = [d for d, _ in domains.most_common(3)]
        for email in emails:
            idx += 1
            swipes.append(_swipe(idx, email, 'spam', folder_route={
                'folderName': name, 'matchType': 'learned', 'source': 'folder-sorting',
            }))

        intent = map_intent(name)
        if intent:
            routes.append({
                'id': f'route-{slugify(name)}', 'name': name,
                'matchType': 'intent', 'matchMode': 'smart', 'matchValue': intent,
            })
            entry['rules'].append(f'Smart category → {intent}')
        else:
            ai_rule = f'Mail like your existing "{name}" folder'
            if top:
                ai_rule += f' — e.g. from {", ".join(top)}'
            routes.append({
                'id': f'route-{slugify(name)}', 'name': name,
                'matchType': 'descriptor', 'matchMode': 'ai', 'aiRule': ai_rule,
            })
            entry['rules'].append(f'AI rule (agent judges; learned from {len(top)} top domains)')

        # Precise strict rules for dominant single domains.
        total = len(emails) or 1
        for dom, count in domains.most_common(3):
            if count >= 3 and count / total >= 0.5:
                routes.append({
                    'id': f'route-{slugify(name)}-{slugify(dom)}', 'name': name,
                    'matchType': 'domain', 'matchMode': 'strict', 'matchValue': dom,
                })
                entry['rules'].append(f'Strict domain → {dom} ({count}/{total})')

        entry['topDomains'] = top
        plan.append(entry)

    settings = {
        'folders': {
            'advancedRoutingEnabled': True,
            'preference': folder_preference,
            'routes': routes,
        },
    }
    return {'swipes': swipes, 'settings': settings, 'plan': plan}


def build_preferences(built: dict) -> dict:
    swipes = built['swipes']
    return {
        'metadata': {
            'generatedAt': _now(),
            'totalSwipes': len(swipes),
            'version': '2.0',
            'source': 'folder-sorting',
            'sessionMode': 'import-sorting',
            'intakePath': 'import-sorting',
        },
        'settings': built['settings'],
        'swipes': swipes,
    }


def load_input(source: str | None) -> dict:
    if source and source != '-':
        with open(source) as f:
            return json.load(f)
    return json.load(sys.stdin)


def main() -> int:
    parser = argparse.ArgumentParser(description='Learn routing rules from existing folder sorting')
    parser.add_argument('input', nargs='?', help='Path to folders JSON (or stdin)')
    parser.add_argument('--preview', action='store_true',
                        help='Print the plan without writing preferences or compiling')
    parser.add_argument('--folder-preference', default=None,
                        help='minimal | moderate | many (overrides input)')
    args = parser.parse_args()

    try:
        data = load_input(args.input)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': f'could not read input: {exc}'}))
        return 1

    folders = data.get('folders') or []
    if not folders:
        print(json.dumps({'ok': False, 'error': 'no folders provided'}))
        return 1

    folder_pref = args.folder_preference or data.get('folderPreference', 'moderate')
    built = build_plan(folders, folder_pref)

    route_count = sum(1 for r in built['settings']['folders']['routes'] if not r.get('action'))
    summary = {
        'foldersAnalyzed': len(built['plan']),
        'emailsAnalyzed': len(built['swipes']),
        'folderRoutesLearned': route_count,
        'plan': built['plan'],
    }

    if args.preview:
        summary['ok'] = True
        summary['preview'] = True
        summary['caution'] = (
            'PREVIEW ONLY — nothing saved. Confirm with the user before applying: '
            'their preferences may have changed and folders can hold stale/lingering mail.'
        )
        print(json.dumps(summary, indent=2))
        return 0

    preferences = build_preferences(built)
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFS_FILE, 'w') as f:
        json.dump(preferences, f, indent=2)
        f.write('\n')

    result = compile_training(PREFS_FILE, USER_DIR, save_settings_from_prefs=True)
    summary['ok'] = result.get('ok', False)
    summary['compile'] = result
    print(json.dumps(summary, indent=2))
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
