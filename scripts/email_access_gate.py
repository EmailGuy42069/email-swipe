"""Email access detection and agent guidance for intake."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from accounts import is_unified_inbox_enabled, list_accounts, unified_inbox_config
from environment_state import (
    DEFAULT_ACCOUNT_KEY,
    account_access_rows,
    environment_summary,
    get_access_record,
    is_access_verified,
    load_environment,
    list_verified_access,
    record_detected_access,
)
from settings import load_settings

SCRIPT_DIR = Path(__file__).resolve().parent


def _load_detect_environment():
    path = SCRIPT_DIR / 'detect-environment.py'
    spec = importlib.util.spec_from_file_location('detect_environment', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _active_account_id(settings: dict) -> str | None:
    cfg = unified_inbox_config(settings)
    if not cfg.get('enabled'):
        return None
    accounts = cfg.get('accounts') or []
    if not accounts:
        return None
    default_id = cfg.get('defaultAccountId')
    if default_id:
        return default_id
    return accounts[0]['id']


def build_email_access_status() -> dict:
    """Scan local environment for mail connectors the agent can use."""
    settings = load_settings()
    env = load_environment()
    unified = is_unified_inbox_enabled(settings)
    account_rows = account_access_rows(settings, env)
    verified_map = list_verified_access(env)

    de = _load_detect_environment()
    providers = []
    for checker in [
        de.check_gog,
        de.check_gmail_api,
        de.check_gmail_mcp,
        de.check_imap,
        de.check_msgraph,
    ]:
        result = checker()
        if result:
            providers.append(result)

    providers.sort(key=lambda x: x.get('priority', 99))
    configured = [p for p in providers if p.get('configured', True)]
    status = de.config_status()

    has_detect = len(configured) > 0
    recommended = configured[0] if configured else None
    active_account_id = _active_account_id(settings)

    if has_detect:
        record_detected_access(
            method=recommended.get('name'),
            account_id=active_account_id,
            address=recommended.get('account'),
        )
        env = load_environment()

    any_verified = len(verified_map) > 0
    all_registered_verified = bool(account_rows) and all(r.get('verified') for r in account_rows)
    active_verified = False
    if unified and active_account_id:
        active_verified = is_access_verified(get_access_record(env, active_account_id))
    elif not unified:
        active_verified = is_access_verified(get_access_record(env, DEFAULT_ACCOUNT_KEY))

    has_access = has_detect or any_verified
    skip_rediscovery = all_registered_verified if unified and account_rows else any_verified

    if unified and account_rows:
        missing = [r['accountId'] for r in account_rows if not r.get('verified')]
        if all_registered_verified:
            gate_message = (
                f'All {len(account_rows)} registered accounts have verified fetch on disk. '
                'Train one account per session; reuse each account fetchHint.'
            )
        elif any_verified:
            gate_message = (
                f'Unified inbox: {len(verified_map)}/{len(account_rows)} accounts verified. '
                f'Verify fetch for: {", ".join(missing)} before injecting those inboxes.'
            )
        elif has_detect:
            gate_message = (
                'Unified inbox enabled. Verify mail access per account (5–10 messages each) '
                'and call record_email_access with accountId before inject.'
            )
        else:
            gate_message = (
                'Unified inbox enabled but no per-account verified access yet. '
                'Ask about connectors per mailbox; see references/unified-inbox.md.'
            )
    elif any_verified:
        rec = get_access_record(env, DEFAULT_ACCOUNT_KEY)
        method = rec.get('method')
        gate_message = (
            f'Verified mail access on disk ({method}). '
            'Reuse fetchHint; skip rediscovery unless fetch fails. '
            'Still confirm real inbox vs demo for this session.'
        )
        if not has_detect:
            has_access = True
    elif has_detect:
        provider_name = recommended.get('name', 'unknown')
        gate_message = (
            f'Mail access detected via {provider_name}. '
            'Verify with a small fetch (5–10 messages) before injecting real inbox mail.'
        )
    else:
        gate_message = (
            'No working mail connector detected on this machine. '
            'Ask the user about existing agent mail tools before setup. '
            'Demo mail is fine for UI-only sessions; real inbox requires access first.'
        )

    blockers: list[str] = []
    missing: list[str] = []
    if unified and account_rows:
        missing = [r['accountId'] for r in account_rows if not r.get('verified')]
        if missing:
            blockers.append(f'Per-account verification missing for: {", ".join(missing)}')
    elif not has_access:
        blockers = [
            'Cannot fetch real inbox until the agent has mail access',
            'Do not guess credentials or skip verification',
        ]

    env_summary = environment_summary(env, settings)

    return {
        'hasAccess': has_access,
        'readyForRealMail': has_access,
        'unifiedInbox': unified,
        'registeredAccounts': list_accounts(settings),
        'accountAccess': account_rows,
        'activeAccountId': active_account_id,
        'activeAccountVerified': active_verified,
        'providers': providers,
        'configuredProviders': configured,
        'recommendedProvider': (
            (get_access_record(env, active_account_id or DEFAULT_ACCOUNT_KEY).get('method') if any_verified else None)
            or (recommended['name'] if recommended else None)
        ),
        'configuration': status,
        'gateMessage': gate_message,
        'blockers': blockers,
        'persisted': env_summary,
        'environment': env_summary,
        'skipRediscovery': skip_rediscovery,
        'agentQuestions': email_access_questions(
            has_access,
            recommended,
            any_verified,
            unified=unified,
            account_rows=account_rows,
            active_account_id=active_account_id,
            active_verified=active_verified,
        ),
        'setupPaths': setup_paths_for_agent(has_access, unified=unified),
        'verifySteps': _verify_steps(unified, account_rows, any_verified),
    }


def _verify_steps(unified: bool, account_rows: list[dict], any_verified: bool) -> list[str]:
    if unified and account_rows:
        steps = [
            'For each registered account: fetch 5–10 inbox messages with that account connector',
            'Confirm id, from/sender, subject, snippet or body per message',
            'record_email_access with accountId + method + fetchHint for each account',
            'Inject one account per session with metadata.accountId',
        ]
        missing = [r['accountId'] for r in account_rows if not r.get('verified')]
        if any_verified and missing:
            steps.insert(0, f'Skip rediscovery for verified accounts; still verify: {", ".join(missing)}')
        return steps
    if any_verified:
        return [
            'Fetch 5–10 recent inbox messages with your mail tool',
            'Confirm each has id, from/sender, subject, snippet or body',
            'Build batch JSON and run inject-emails.py',
            'Call record_email_access (method + fetchHint; accountId when unified inbox)',
        ]
    return [
        'Ask: which provider (Gmail, Outlook, IMAP, other)?',
        'Ask: do you already have mail connected to this agent (MCP, CLI, API)?',
        'If yes — use that tool; if no — see references/email-access-gate.md',
        'Re-run check_email_access after setup',
        'After a successful fetch, call record_email_access',
    ]


def email_access_questions(
    has_access: bool,
    recommended: dict | None,
    any_verified: bool = False,
    *,
    unified: bool = False,
    account_rows: list[dict] | None = None,
    active_account_id: str | None = None,
    active_verified: bool = False,
) -> list[dict]:
    """Questions the agent must resolve before real-mail training."""
    questions = []
    account_rows = account_rows or []

    if unified and account_rows:
        if not active_verified:
            active = next((r for r in account_rows if r['accountId'] == active_account_id), account_rows[0])
            questions.append({
                'id': 'verify_active_account',
                'prompt': (
                    f'Unified inbox: verify fetch for {active.get("label")} ({active["accountId"]}) '
                    f'via {active.get("connectorHint") or "your mail tool"} before this training session.'
                ),
                'why': 'Each mailbox may use a different connector; verify per accountId.',
                'required': True,
            })
        else:
            active = next((r for r in account_rows if r['accountId'] == active_account_id), None)
            label = (active or {}).get('label') or active_account_id
            questions.append({
                'id': 'real_or_demo',
                'prompt': (
                    f'Verified access for {label}. Pull real mail for this account, or use demo emails?'
                ),
                'why': 'Active account is verified — confirm real vs demo only.',
                'required': True,
            })
        missing = [r for r in account_rows if not r.get('verified')]
        if missing:
            questions.append({
                'id': 'other_accounts_pending',
                'prompt': (
                    'Other registered accounts still need verified fetch on disk: '
                    + ', '.join(f'{r["label"]} ({r["accountId"]})' for r in missing)
                    + '. Train them in separate sessions after verifying each.'
                ),
                'why': 'Unified inbox trains one account per session.',
                'required': False,
            })
        return questions

    if not any_verified:
        questions.append({
            'id': 'agent_has_mail_access',
            'prompt': (
                'Do I already have access to your email from another tool '
                '(Gmail MCP, gog CLI, IMAP, Microsoft Graph, or similar)?'
            ),
            'why': 'Separates ready-to-fetch from setup-required. Ask even if auto-detect found nothing.',
            'required': True,
        })
        questions.append({
            'id': 'email_provider',
            'prompt': 'Which email provider is this? (Gmail, Outlook/Microsoft 365, Fastmail, iCloud, work Exchange, other)',
            'why': 'Chooses the right setup path when access is missing.',
            'required': not has_access,
        })

    if any_verified:
        rec = get_access_record(load_environment(), DEFAULT_ACCOUNT_KEY)
        name = rec.get('method') or (recommended or {}).get('name') or 'saved connector'
        questions.append({
            'id': 'real_or_demo',
            'prompt': (
                f'I already have verified mail access via {name}. '
                'Pull from your real inbox for training, or start with demo emails?'
            ),
            'why': 'Access is known — only confirm real vs demo.',
            'required': True,
        })
    elif has_access and recommended:
        name = recommended.get('name', 'detected connector')
        questions.append({
            'id': 'real_or_demo',
            'prompt': (
                f'I detected {name} on this machine. Pull a sample of your real inbox for training, '
                'or start with demo emails to learn the UI first?'
            ),
            'why': 'User chooses real mail vs demo when access exists.',
            'required': True,
        })
    elif not has_access:
        questions.append({
            'id': 'real_or_demo',
            'prompt': (
                'I do not have working mail access yet. We can (a) connect your email first, '
                '(b) use demo emails to try the swipe UI, or (c) pause until mail is set up. Which do you prefer?'
            ),
            'why': 'Never silently substitute demo when user asked for real inbox.',
            'required': True,
        })

    return questions


def setup_paths_for_agent(has_access: bool, *, unified: bool = False) -> list[dict]:
    """Ordered setup options when access is missing."""
    if unified:
        return [
            {
                'id': 'per_account_verify',
                'label': 'Verify each registered account separately',
                'steps': [
                    'set_mail_accounts / get_agent_spine for registry',
                    'Fetch 5–10 messages per accountId with that account connector',
                    'record_email_access per accountId with method + fetchHint',
                    'inject-emails.py with metadata.accountId — one account per session',
                ],
            },
            {'id': 'demo_fallback', 'label': 'Demo only for one account at a time'},
        ]

    if has_access:
        return [
            {'id': 'verify_fetch', 'label': 'Verify with 5–10 message fetch, then inject-emails.py'},
            {'id': 'demo_fallback', 'label': 'User chose demo — session-intake.py demo or empty emails.json fallback'},
        ]

    return [
        {
            'id': 'existing_agent_tool',
            'label': 'User already has mail on this agent',
            'steps': [
                'Use their Gmail MCP / Graph / IMAP skill to fetch inbox messages',
                'Normalize to batch JSON (id, from, subject, snippet, html optional)',
                'inject-emails.py → re-run check_email_access',
            ],
        },
        {
            'id': 'gog_gmail',
            'label': 'Gmail via gog CLI (local)',
            'steps': [
                'Install gog; user runs: gog auth login',
                'python scripts/setup-config.py (set EMAIL_SWIPE_EMAIL)',
                'python scripts/fetch-emails.py --limit 10 to verify',
            ],
        },
        {
            'id': 'manual_batch',
            'label': 'User exports / pastes mail',
            'steps': [
                'User provides a JSON batch or you build from their paste',
                'inject-emails.py batch.json — no live connector required',
            ],
        },
        {
            'id': 'demo_only',
            'label': 'Demo only (no real mail)',
            'steps': [
                'session-intake.py demo OR serve-ui.py with demo-emails.json fallback',
                'Tell user this does not train on their real preferences',
            ],
        },
    ]
