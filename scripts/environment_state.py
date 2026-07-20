#!/usr/bin/env python3
"""Persisted machine environment — verified mail access and UI open hints.

Skill how-tos stay in the skill (get_skill_context / AGENTS.md).
This file stores what this machine has already proven works per account.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import USER_DIR, load_settings

ENVIRONMENT_FILE = USER_DIR / 'environment.json'
DEFAULT_ACCOUNT_KEY = '_default'

DEFAULT_ACCESS_RECORD: dict[str, Any] = {
    'verified': False,
    'verifiedAt': None,
    'method': None,
    'provider': None,
    'address': None,
    'fetchHint': None,
    'notes': None,
    'source': None,
    'lastDetectedAt': None,
    'lastDetectedMethod': None,
}

DEFAULT_ENVIRONMENT: dict[str, Any] = {
    'version': '1.1',
    'updatedAt': None,
    'emailAccessByAccount': {},
    'emailAccess': None,
    'ui': {
        'openHint': (
            'Run `python scripts/serve-ui.py` and open the Desktop URL printed at startup '
            '(or read ~/.config/email-swipe/runtime.json).'
        ),
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_environment() -> dict[str, Any]:
    return deepcopy(DEFAULT_ENVIRONMENT)


def _normalize_account_id(account_id: str | None) -> str:
    raw = (account_id or '').strip().lower()
    return raw or DEFAULT_ACCOUNT_KEY


def _empty_access_record() -> dict[str, Any]:
    return deepcopy(DEFAULT_ACCESS_RECORD)


def _migrate_legacy_email_access(env: dict[str, Any]) -> dict[str, Any]:
    """Move legacy single emailAccess block into emailAccessByAccount."""
    legacy = env.get('emailAccess')
    by_account = env.setdefault('emailAccessByAccount', {})
    if not isinstance(by_account, dict):
        by_account = {}
        env['emailAccessByAccount'] = by_account
    if isinstance(legacy, dict) and legacy.get('verified') and legacy.get('method'):
        key = DEFAULT_ACCOUNT_KEY
        if legacy.get('accountId'):
            key = _normalize_account_id(legacy['accountId'])
        elif legacy.get('account'):
            key = DEFAULT_ACCOUNT_KEY
        if key not in by_account:
            rec = _empty_access_record()
            rec.update(legacy)
            if legacy.get('account') and not rec.get('address'):
                rec['address'] = legacy['account']
            by_account[key] = rec
    env['emailAccess'] = None
    return env


def load_environment() -> dict[str, Any]:
    env = default_environment()
    if not ENVIRONMENT_FILE.exists():
        return env
    try:
        with open(ENVIRONMENT_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return env
    if not isinstance(data, dict):
        return env

    env['version'] = data.get('version') or env['version']
    env['updatedAt'] = data.get('updatedAt')
    if isinstance(data.get('ui'), dict):
        ui = deepcopy(DEFAULT_ENVIRONMENT['ui'])
        ui.update(data['ui'])
        env['ui'] = ui
    if isinstance(data.get('emailAccessByAccount'), dict):
        env['emailAccessByAccount'] = deepcopy(data['emailAccessByAccount'])
    if isinstance(data.get('emailAccess'), dict):
        env['emailAccess'] = deepcopy(data['emailAccess'])

    env = _migrate_legacy_email_access(env)
    return env


def save_environment(env: dict[str, Any]) -> dict[str, Any]:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    out = deepcopy(env)
    out['version'] = '1.1'
    out['updatedAt'] = _now()
    out['emailAccess'] = None
    with open(ENVIRONMENT_FILE, 'w') as f:
        json.dump(out, f, indent=2)
        f.write('\n')
    return out


def get_access_record(env: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
    env = env if env.get('emailAccessByAccount') is not None else load_environment()
    by_account = env.get('emailAccessByAccount') or {}
    key = _normalize_account_id(account_id)
    rec = by_account.get(key)
    if isinstance(rec, dict):
        merged = _empty_access_record()
        merged.update(rec)
        return merged
    return _empty_access_record()


def is_access_verified(record: dict[str, Any] | None) -> bool:
    return bool(record and record.get('verified') and record.get('method'))


def list_verified_access(env: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    env = env or load_environment()
    by_account = env.get('emailAccessByAccount') or {}
    return {
        aid: rec
        for aid, rec in by_account.items()
        if isinstance(rec, dict) and is_access_verified(rec)
    }


def record_detected_access(
    *,
    method: str | None,
    account_id: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """Soft note from auto-detect — does not mark verified."""
    env = load_environment()
    key = _normalize_account_id(account_id)
    by_account = env.setdefault('emailAccessByAccount', {})
    rec = get_access_record(env, key)
    rec['lastDetectedAt'] = _now()
    rec['lastDetectedMethod'] = method
    if address and not rec.get('address'):
        rec['address'] = address
    by_account[key] = rec
    return save_environment(env)


def record_verified_access(
    *,
    method: str,
    account_id: str | None = None,
    provider: str | None = None,
    address: str | None = None,
    fetch_hint: str | None = None,
    notes: str | None = None,
    source: str = 'agent',
) -> dict[str, Any]:
    """Agent confirmed a successful fetch — skip rediscovery for this account next session."""
    if not method or not str(method).strip():
        raise ValueError('method is required')
    env = load_environment()
    key = _normalize_account_id(account_id)
    by_account = env.setdefault('emailAccessByAccount', {})
    rec = get_access_record(env, key)
    rec['verified'] = True
    rec['verifiedAt'] = _now()
    rec['method'] = str(method).strip()
    rec['provider'] = (provider or '').strip() or None
    rec['address'] = (address or '').strip() or rec.get('address')
    rec['fetchHint'] = (fetch_hint or '').strip() or None
    rec['notes'] = (notes or '').strip() or None
    rec['source'] = source
    rec['lastDetectedAt'] = rec.get('lastDetectedAt') or rec['verifiedAt']
    rec['lastDetectedMethod'] = rec.get('lastDetectedMethod') or rec['method']
    by_account[key] = rec
    return save_environment(env)


def clear_verified_access(
    *,
    account_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    env = load_environment()
    by_account = env.setdefault('emailAccessByAccount', {})

    if account_id is None:
        cleared: dict[str, Any] = {}
        for key, rec in list(by_account.items()):
            if not isinstance(rec, dict):
                continue
            out = _empty_access_record()
            out['notes'] = reason
            out['lastDetectedAt'] = rec.get('lastDetectedAt')
            out['lastDetectedMethod'] = rec.get('lastDetectedMethod')
            cleared[key] = out
        env['emailAccessByAccount'] = cleared
        return save_environment(env)

    key = _normalize_account_id(account_id)
    prev = get_access_record(env, key)
    rec = _empty_access_record()
    rec['notes'] = reason
    rec['lastDetectedAt'] = prev.get('lastDetectedAt')
    rec['lastDetectedMethod'] = prev.get('lastDetectedMethod')
    by_account[key] = rec
    return save_environment(env)


def account_access_rows(settings: dict | None = None, env: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Merge spine account registry with per-account verified access."""
    from accounts import list_accounts, unified_inbox_config

    settings = settings or load_settings()
    env = env or load_environment()
    cfg = unified_inbox_config(settings)
    accounts = list_accounts(settings)
    verified = list_verified_access(env)

    if accounts:
        rows = []
        for acc in accounts:
            aid = acc['id']
            rec = get_access_record(env, aid)
            rows.append({
                'accountId': aid,
                'label': acc.get('label', aid),
                'provider': acc.get('provider'),
                'address': acc.get('address') or rec.get('address'),
                'connectorHint': acc.get('connectorHint'),
                'verified': is_access_verified(rec),
                'method': rec.get('method'),
                'fetchHint': rec.get('fetchHint'),
                'verifiedAt': rec.get('verifiedAt'),
            })
        return rows

    rec = get_access_record(env, DEFAULT_ACCOUNT_KEY)
    if is_access_verified(rec) or rec.get('lastDetectedMethod'):
        return [{
            'accountId': DEFAULT_ACCOUNT_KEY,
            'label': 'Default inbox',
            'provider': rec.get('provider'),
            'address': rec.get('address'),
            'connectorHint': None,
            'verified': is_access_verified(rec),
            'method': rec.get('method'),
            'fetchHint': rec.get('fetchHint'),
            'verifiedAt': rec.get('verifiedAt'),
        }]
    return []


def environment_summary(
    env: dict[str, Any] | None = None,
    settings: dict | None = None,
) -> dict[str, Any]:
    env = env or load_environment()
    settings = settings or load_settings()
    from accounts import unified_inbox_config

    rows = account_access_rows(settings, env)
    verified_rows = [r for r in rows if r.get('verified')]
    unified = bool(unified_inbox_config(settings).get('enabled'))

    if unified and rows:
        missing = [r['accountId'] for r in rows if not r.get('verified')]
        guidance = (
            f'Unified inbox: {len(verified_rows)}/{len(rows)} accounts verified on disk. '
            'Verify fetch per account before inject; call record_email_access with accountId.'
        )
        if missing:
            guidance += f' Still need: {", ".join(missing)}.'
    elif verified_rows:
        rec = verified_rows[0]
        guidance = (
            f'Verified mail access for {rec.get("label") or rec["accountId"]} ({rec.get("method")}). '
            'Reuse fetchHint; skip rediscovery unless fetch fails. Still confirm real vs demo.'
        )
    else:
        guidance = (
            'No verified mail access yet. Run check_email_access, verify a small fetch per account, '
            'then record_email_access (include accountId when unified inbox is enabled).'
        )

    return {
        'file': str(ENVIRONMENT_FILE),
        'unifiedInbox': unified,
        'verified': len(verified_rows) > 0,
        'verifiedAccountCount': len(verified_rows),
        'registeredAccountCount': len(rows),
        'accounts': rows,
        'emailAccessByAccount': env.get('emailAccessByAccount') or {},
        'uiOpenHint': (env.get('ui') or {}).get('openHint'),
        'guidance': guidance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Email Swipe environment state (verified mail access)')
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('show', help='Print environment.json')
    sub.add_parser('summary', help='Print short summary')

    rec = sub.add_parser('record', help='Record verified mail access after a successful fetch')
    rec.add_argument('--method', required=True, help='gog, gmail-mcp, imap, msgraph, manual-batch, …')
    rec.add_argument('--account-id', default=None, help='Unified inbox account slug (omit for single inbox)')
    rec.add_argument('--provider', default=None)
    rec.add_argument('--address', default=None, help='Email address for this account')
    rec.add_argument('--account', default=None, help='Deprecated alias for --address')
    rec.add_argument('--fetch-hint', default=None)
    rec.add_argument('--notes', default=None)

    clr = sub.add_parser('clear', help='Clear verified access')
    clr.add_argument('--account-id', default=None, help='Clear one account; omit to clear all')
    clr.add_argument('--reason', default=None)

    args = parser.parse_args()
    if args.cmd == 'show':
        print(json.dumps(load_environment(), indent=2))
        return 0
    if args.cmd == 'summary':
        print(json.dumps(environment_summary(), indent=2))
        return 0
    if args.cmd == 'record':
        env = record_verified_access(
            method=args.method,
            account_id=args.account_id,
            provider=args.provider,
            address=args.address or args.account,
            fetch_hint=args.fetch_hint,
            notes=args.notes,
            source='cli',
        )
        print(json.dumps(env, indent=2))
        return 0
    if args.cmd == 'clear':
        print(json.dumps(clear_verified_access(account_id=args.account_id, reason=args.reason), indent=2))
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
