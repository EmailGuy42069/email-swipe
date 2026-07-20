#!/usr/bin/env python3
"""Shared user settings — minimal surface (agent on/off). Context via agent chat."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

USER_DIR = Path.home() / '.config' / 'email-swipe'
SETTINGS_FILE = USER_DIR / 'settings.json'
UI_SETTINGS_FILE = Path(__file__).resolve().parent.parent / 'assets' / 'ui' / 'settings.json'

from accounts import default_unified_inbox, list_accounts, unified_inbox_config

DEFAULT_SETTINGS = {
    'version': '2.0',
    'updatedAt': None,
    'agent': {
        'enabled': False,
        'name': '',
        'scanFrequency': 'twice_daily',
        'autonomyLevel': 'recommend',
    },
    'folders': {
        'preference': 'minimal',
        'includeUrgentFolder': True,
        'urgentFolderName': 'Needs Attention',
    },
    'unifiedInbox': default_unified_inbox(),
    'access': {
        'exploreRemoteReachability': False,
    },
    'rhythm': {
        'preferredTimes': ['08:00', '17:00'],
        'digestStyle': 'short',
        'digestSections': ['needs_reply', 'score_trend', 'training_gaps'],
        'includeScoreTrend': True,
        'quietHours': None,
    },
    'platformRules': {
        'mode': 'suggest_only',
        'neverRemoveFromInbox': True,
        'allowedActions': ['label', 'star'],
        'forbiddenActions': ['delete', 'skip_inbox', 'auto_archive', 'block_sender'],
        'maxSuggestedRules': 12,
    },
    'context': {
        'problemToSolve': '',
        'notes': '',
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(path: Path | None = None) -> dict:
    settings = deepcopy(DEFAULT_SETTINGS)

    if path and path.exists():
        settings = _deep_merge(settings, _load_json_file(path))
    else:
        for candidate in (SETTINGS_FILE, UI_SETTINGS_FILE):
            if candidate.exists():
                settings = _deep_merge(settings, _load_json_file(candidate))

    if os.environ.get('EMAIL_SWIPE_AGENT_ENABLED', '').lower() in ('1', 'true', 'yes'):
        settings['agent']['enabled'] = True

    return settings


def _load_json_file(path: Path) -> dict:
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict, path: Path | None = None) -> Path:
    target = path or SETTINGS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = _deep_merge(DEFAULT_SETTINGS, settings)
    settings['updatedAt'] = datetime.now(timezone.utc).isoformat()
    with open(target, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    return target


def settings_status(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    context = settings.get('context', {})
    has_context = any(context.get(k, '').strip() for k in ('job', 'life', 'problemToSolve', 'notes'))

    return {
        'settingsFile': str(SETTINGS_FILE) if SETTINGS_FILE.exists() else None,
        'agentEnabled': settings.get('agent', {}).get('enabled', False),
        'folderPreference': settings.get('folders', {}).get('preference', 'minimal'),
        'urgentFolder': settings.get('folders', {}).get('urgentFolderName', 'Needs Attention'),
        'hasUserContext': has_context,
        'unifiedInboxEnabled': unified_inbox_config(settings).get('enabled', False),
        'mailAccountCount': len(list_accounts(settings)),
        'exploreRemoteReachability': bool((settings.get('access') or {}).get('exploreRemoteReachability')),
        'autonomyLevel': settings.get('agent', {}).get('autonomyLevel', 'recommend'),
    }


def folder_budget(preference: str) -> int:
    return {'minimal': 2, 'moderate': 5, 'many': 12}.get(preference, 2)


SETTINGS_PATCH_KEYS = frozenset({
    'version',
    'agent',
    'folders',
    'unifiedInbox',
    'access',
    'rhythm',
    'platformRules',
    'context',
})


def apply_settings_patch(settings: dict, patch: dict) -> dict:
    """Deep-merge an allowed settings patch into current settings."""
    if not isinstance(patch, dict):
        raise ValueError('settings patch must be a JSON object')
    filtered = {k: v for k, v in patch.items() if k in SETTINGS_PATCH_KEYS}
    if not filtered and patch:
        raise ValueError(f'patch must use keys from: {sorted(SETTINGS_PATCH_KEYS)}')
    return _deep_merge(settings, filtered)


def update_settings(patch: dict, *, compile_after: bool = False) -> dict:
    """Persist a settings patch. Optionally recompile when preferences exist."""
    current = load_settings(SETTINGS_FILE if SETTINGS_FILE.exists() else None)
    merged = apply_settings_patch(current, patch)
    target = save_settings(merged)
    result = {
        'ok': True,
        'settingsFile': str(target),
        'settings': merged,
        'status': settings_status(merged),
    }
    if compile_after:
        prefs = USER_DIR / 'preferences.json'
        if prefs.exists():
            from compile_training import compile_training

            compile_result = compile_training(
                prefs,
                USER_DIR,
                save_settings_from_prefs=False,
                session_id=None,
            )
            result['compile'] = compile_result
        else:
            result['compile'] = {'ok': False, 'error': 'no preferences.json — complete a swipe session first'}
    return result


def build_settings_api_payload() -> dict:
    """Payload shared by serve-ui GET /api/settings and MCP get_settings."""
    settings = load_settings(SETTINGS_FILE if SETTINGS_FILE.exists() else None)
    payload: dict = {
        'settings': settings,
        'settingsFile': str(SETTINGS_FILE) if SETTINGS_FILE.exists() else None,
        'status': settings_status(settings),
    }
    try:
        from accounts import account_training_status

        payload['accountsStatus'] = account_training_status(settings)
    except Exception:
        payload['accountsStatus'] = []
    try:
        from script_imports import session_intake_mod

        if session_intake_mod.INTAKE_FILE.exists():
            payload['intake'] = session_intake_mod.load_intake()
    except Exception:
        pass
    try:
        from session_state import build_session_status, load_runtime

        payload['runtime'] = load_runtime() or None
        payload['sessionStatus'] = build_session_status()
    except Exception:
        pass
    return payload
