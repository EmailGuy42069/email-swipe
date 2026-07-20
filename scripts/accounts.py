"""Unified inbox account registry helpers."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from settings import USER_DIR

_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')


def default_unified_inbox() -> dict:
    return {
        'enabled': False,
        'defaultAccountId': None,
        'accounts': [],
    }


def unified_inbox_config(settings: dict | None) -> dict:
    settings = settings or {}
    base = default_unified_inbox()
    raw = settings.get('unifiedInbox') or {}
    if not isinstance(raw, dict):
        return base
    merged = {**base, **raw}
    accounts = merged.get('accounts') or []
    merged['accounts'] = [a for a in accounts if isinstance(a, dict) and a.get('id')]
    return merged


def is_unified_inbox_enabled(settings: dict | None) -> bool:
    return bool(unified_inbox_config(settings).get('enabled'))


def list_accounts(settings: dict | None) -> list[dict]:
    cfg = unified_inbox_config(settings)
    if not cfg.get('enabled'):
        return []
    return cfg.get('accounts') or []


def account_label(settings: dict | None, account_id: str | None) -> str | None:
    if not account_id:
        return None
    for account in list_accounts(settings):
        if account.get('id') == account_id:
            return account.get('label') or account_id
    return account_id


def normalize_account(account: dict) -> dict | None:
    if not isinstance(account, dict):
        return None
    account_id = (account.get('id') or '').strip().lower()
    label = (account.get('label') or '').strip()
    if not account_id or not _SLUG_RE.match(account_id) or not label:
        return None
    out = {
        'id': account_id,
        'label': label,
        'provider': (account.get('provider') or 'other').strip().lower(),
    }
    for key in ('role', 'address', 'connectorHint'):
        val = account.get(key)
        if val:
            out[key] = str(val).strip()
    return out


def merge_accounts(settings: dict, accounts: list[dict]) -> dict:
    """Replace account list while preserving enabled flag."""
    settings = dict(settings or {})
    cfg = unified_inbox_config(settings)
    normalized = []
    seen = set()
    for raw in accounts or []:
        acc = normalize_account(raw)
        if not acc or acc['id'] in seen:
            continue
        seen.add(acc['id'])
        normalized.append(acc)
    cfg['accounts'] = normalized
    default_id = cfg.get('defaultAccountId')
    if default_id and default_id not in seen:
        cfg['defaultAccountId'] = normalized[0]['id'] if normalized else None
    elif not default_id and normalized:
        cfg['defaultAccountId'] = normalized[0]['id']
    settings['unifiedInbox'] = cfg
    return settings


def accounts_for_policy_graph(settings: dict | None) -> list[dict]:
    cfg = unified_inbox_config(settings)
    if not cfg.get('enabled'):
        return []
    return [
        {
            'id': a['id'],
            'label': a.get('label', a['id']),
            'provider': a.get('provider'),
            'role': a.get('role'),
            'address': a.get('address'),
        }
        for a in cfg.get('accounts') or []
    ]


def account_training_status(settings: dict | None, prefs_path: Path | None = None) -> list[dict]:
    """Per-account training status for the Inboxes settings tab."""
    cfg = unified_inbox_config(settings)
    accounts = cfg.get('accounts') or []
    if not accounts:
        return []

    swipe_counts: dict[str, int] = defaultdict(int)
    prefs_path = prefs_path or (USER_DIR / 'preferences.json')
    if prefs_path.exists():
        try:
            with open(prefs_path) as f:
                prefs = json.load(f)
            session_aid = (prefs.get('metadata') or {}).get('accountId')
            for swipe in prefs.get('swipes') or []:
                aid = swipe.get('accountId') or session_aid
                if aid:
                    swipe_counts[aid] += 1
        except (json.JSONDecodeError, OSError):
            pass

    history_swipes: dict[str, int] = defaultdict(int)
    try:
        from session_state import load_session_history

        for session in load_session_history().get('sessions') or []:
            aid = session.get('accountId')
            if aid:
                history_swipes[aid] += int(session.get('swipeCount') or 0)
    except Exception:
        pass

    brief_accounts: set[str] = set()
    brief_path = USER_DIR / 'assistant-brief.md'
    if brief_path.exists():
        try:
            text = brief_path.read_text(encoding='utf-8')
            for acc in accounts:
                aid = acc.get('id', '')
                if aid and f'`{aid}`' in text:
                    brief_accounts.add(aid)
        except OSError:
            pass

    result = []
    for acc in accounts:
        aid = acc['id']
        swipe_count = max(swipe_counts.get(aid, 0), history_swipes.get(aid, 0))
        in_brief = aid in brief_accounts
        trained = swipe_count > 0 or in_brief
        if in_brief and swipe_count == 0:
            status_label = 'In brief'
        elif trained:
            noun = 'swipe' if swipe_count == 1 else 'swipes'
            status_label = f'Trained ({swipe_count} {noun})'
        else:
            status_label = 'Not trained yet'
        result.append({
            **acc,
            'swipeCount': swipe_count,
            'trained': trained,
            'inBrief': in_brief,
            'status': 'trained' if trained else 'not_trained',
            'statusLabel': status_label,
        })
    return result
