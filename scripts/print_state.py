#!/usr/bin/env python3
"""Print authoritative Email Swipe state locations and current files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from session_state import (
    RUNTIME_FILE,
    SESSION_COMPLETE_FILE,
    SESSION_HISTORY_FILE,
    build_session_status,
    load_runtime,
)
from settings import SETTINGS_FILE, USER_DIR, load_settings, settings_status
from environment_state import ENVIRONMENT_FILE, environment_summary, load_environment

ARTIFACTS = {
    'preferences.json': USER_DIR / 'preferences.json',
    'settings.json': SETTINGS_FILE,
    'environment.json': ENVIRONMENT_FILE,
    'training-pack.json': USER_DIR / 'training-pack.json',
    'assistant-brief.md': USER_DIR / 'assistant-brief.md',
    'policy-graph.json': USER_DIR / 'policy-graph.json',
    'calibration.json': USER_DIR / 'calibration.json',
    'platform-rules.json': USER_DIR / 'platform-rules.json',
    'runtime.json': RUNTIME_FILE,
    'session-complete.json': SESSION_COMPLETE_FILE,
    'session-history.json': SESSION_HISTORY_FILE,
}

BROWSER_CACHE_ONLY = [
    'localStorage (email-swipe-settings) — cache until compile or POST /api/settings',
    'IndexedDB (EmailSwipe preferences store) — in-progress swipes only',
    'sessionStorage (email-swipe-inbox-fp) — session fingerprint',
    'assets/ui/settings.json — dev fallback only; not authoritative',
]


def file_row(path: Path) -> dict:
    if not path.exists():
        return {'path': str(path), 'exists': False}
    stat = path.stat()
    return {
        'path': str(path),
        'exists': True,
        'sizeBytes': stat.st_size,
        'modifiedAt': stat.st_mtime,
    }


def build_report() -> dict:
    settings = load_settings()
    runtime = load_runtime()
    environment = load_environment()
    return {
        'userDir': str(USER_DIR),
        'authoritative': {
            'settings': str(SETTINGS_FILE),
            'preferences': str(USER_DIR / 'preferences.json'),
            'environment': str(ENVIRONMENT_FILE),
            'compiledArtifacts': str(USER_DIR),
        },
        'browserCacheOnly': BROWSER_CACHE_ONLY,
        'settings': settings_status(settings),
        'environment': environment_summary(environment),
        'runtime': runtime or None,
        'sessionStatus': build_session_status(),
        'files': {name: file_row(path) for name, path in ARTIFACTS.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Print Email Swipe authoritative state summary')
    parser.add_argument('--json', action='store_true', help='Output JSON only')
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print('Email Swipe — state ownership')
    print(f'  User dir: {report["userDir"]}')
    print(f'  Settings truth: {report["authoritative"]["settings"]}')
    print(f'  Swipe export truth: {report["authoritative"]["preferences"]}')
    print(f'  Environment: {report["authoritative"]["environment"]}')
    env = report['environment']
    if env.get('unifiedInbox') and env.get('registeredAccountCount'):
        print(
            f"  Verified mail: {env.get('verifiedAccountCount', 0)}/"
            f"{env['registeredAccountCount']} accounts"
        )
        for row in env.get('accounts') or []:
            flag = 'yes' if row.get('verified') else 'no'
            print(f"    [{flag}] {row.get('accountId')}: {row.get('method') or 'not verified'}")
    elif env.get('verified'):
        rows = [r for r in env.get('accounts') or [] if r.get('verified')]
        if rows:
            rec = rows[0]
            print(f"  Verified mail: {rec.get('method')} ({rec.get('label') or rec.get('accountId')})")
        else:
            print('  Verified mail: yes')
    else:
        print('  Verified mail: (none yet — record_email_access after fetch)')
    print('')
    print('Files:')
    for name, row in report['files'].items():
        flag = 'yes' if row['exists'] else 'no'
        print(f'  [{flag}] {name}: {row["path"]}')
    print('')
    print('Browser stores (cache only):')
    for line in BROWSER_CACHE_ONLY:
        print(f'  - {line}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
