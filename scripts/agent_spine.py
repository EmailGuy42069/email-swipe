#!/usr/bin/env python3
"""Agent spine — structured settings view for agent source-of-truth sync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from settings import DEFAULT_SETTINGS, build_settings_api_payload, load_settings

SPINE_DOC = 'references/agent-spine.md'

# Sections the agent tracks; most are dormant until explicitly active.
SECTION_KEYS = (
    'agent',
    'agent.postTraining',
    'unifiedInbox',
    'sorting.advanced',
    'rules.autonomy',
    'rules.platform',
    'rhythm',
    'access.remote',
    'context',
)

DEFAULT_DORMANT = [
    'unifiedInbox',
    'sorting.advanced',
    'rules.autonomy',
    'rules.platform',
    'rhythm',
    'access.remote',
    'context',
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_active_sections(settings: dict) -> list[str]:
    """Return which advanced sections are in play for agent behavior."""
    active: list[str] = []
    agent = settings.get('agent') or {}
    folders = settings.get('folders') or {}
    unified = settings.get('unifiedInbox') or {}
    access = settings.get('access') or {}
    context = settings.get('context') or {}
    rhythm = settings.get('rhythm') or {}
    rules = settings.get('platformRules') or {}

    if (agent.get('name') or '').strip():
        active.append('agent')
    if agent.get('enabled'):
        active.append('agent.postTraining')
    if unified.get('enabled'):
        active.append('unifiedInbox')
    if folders.get('advancedRoutingEnabled'):
        active.append('sorting.advanced')
    if agent.get('autonomyLevel', 'recommend') != 'recommend':
        active.append('rules.autonomy')
    if rules.get('mode') != 'suggest_only' or rules.get('maxSuggestedRules', 12) != 12:
        active.append('rules.platform')
    forbidden = set(rules.get('forbiddenActions') or [])
    default_forbidden = set(DEFAULT_SETTINGS['platformRules']['forbiddenActions'])
    if forbidden != default_forbidden:
        if 'rules.platform' not in active:
            active.append('rules.platform')
    if access.get('exploreRemoteReachability'):
        active.append('access.remote')
    if (context.get('problemToSolve') or '').strip() or (context.get('notes') or '').strip():
        active.append('context')
    scan = agent.get('scanFrequency', 'twice_daily')
    default_times = DEFAULT_SETTINGS['rhythm']['preferredTimes']
    preferred = rhythm.get('preferredTimes') or []
    if scan not in ('off', 'twice_daily') or preferred != default_times:
        active.append('rhythm')
    if rhythm.get('digestStyle', 'short') != 'short':
        if 'rhythm' not in active:
            active.append('rhythm')

    return active


def infer_dormant_sections(active: list[str]) -> list[str]:
    return [s for s in SECTION_KEYS if s not in active]


def build_agent_spine(*, source: str = 'disk') -> dict[str, Any]:
    """Hydrate agent spine from authoritative disk mirror (via settings API payload)."""
    payload = build_settings_api_payload()
    settings = payload.get('settings') or load_settings()
    active = infer_active_sections(settings)
    return {
        'version': '1.0',
        'doc': SPINE_DOC,
        'sourceOfTruth': 'agent',
        'diskMirror': payload.get('settingsFile'),
        'settings': settings,
        'activeSections': active,
        'dormantSections': infer_dormant_sections(active),
        'accountsStatus': payload.get('accountsStatus') or [],
        'intake': payload.get('intake'),
        'runtime': payload.get('runtime'),
        'sessionStatus': payload.get('sessionStatus'),
        'status': payload.get('status'),
        'lastSync': {
            'from': source,
            'at': _now_iso(),
        },
        'protocol': {
            'beforeOpenUi': ['update_settings(spine.settings)', 'serve-ui.py', 'Desktop URL'],
            'afterUiFeedback': ['get_agent_spine or get_settings', 'merge into agent memory'],
            'beforeMailAction': ['check activeSections', 'use policy-graph + brief'],
        },
    }


def spine_summary_lines(spine: dict | None = None) -> list[str]:
    spine = spine or build_agent_spine()
    active = spine.get('activeSections') or []
    dormant = spine.get('dormantSections') or []
    return [
        f'Agent spine: {len(active)} active, {len(dormant)} dormant — see {SPINE_DOC}',
        f'Active: {", ".join(active) if active else "(none — defaults only)"}',
        'Before UI: update_settings. After UI: get_agent_spine.',
    ]
