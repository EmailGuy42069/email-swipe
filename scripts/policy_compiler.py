#!/usr/bin/env python3
"""Policy graph, calibration, and human-readable assistant brief from swipe training."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from folder_intent import INTENT_DEFINITIONS, score_intent
from session_state import compute_score_trend, load_session_history

from accounts import account_label, accounts_for_policy_graph, is_unified_inbox_enabled, list_accounts

URGENT_KEYWORDS = (
    'urgent', 'action required', 'deadline', 'expires', 'overdue',
    'security alert', 'verify your account', 'payment failed', 'past due',
    'respond by', 'time sensitive', 'immediate attention',
)

ACTION_LABELS = {
    'spam': "don't keep",
    'keep': 'keep',
    'important': 'important',
    'needs_attention': 'important',
}

HARD_CONSTRAINTS = [
    'never_auto_delete',
    'never_skip_inbox_without_approval',
]

DEFAULT_AUTONOMY = 'recommend'
VALID_AUTONOMY_LEVELS = frozenset({'recommend', 'approve_batch', 'auto_safe'})


def resolve_autonomy_level(settings: dict | None) -> str:
    level = (settings or {}).get('agent', {}).get('autonomyLevel', DEFAULT_AUTONOMY)
    return level if level in VALID_AUTONOMY_LEVELS else DEFAULT_AUTONOMY


def extract_domain(address: str) -> str:
    if '@' in address:
        return address.split('@', 1)[1].lower().strip('>')
    return ''


def normalize_swipes(preferences: dict) -> list[dict]:
    swipes = preferences.get('swipes')
    if swipes:
        return swipes
    reconstructed = []
    for example in preferences.get('fewShotExamples', []):
        email = example.get('email', {})
        reconstructed.append({
            'from': email.get('sender', ''),
            'sender': email.get('sender', ''),
            'subject': email.get('subject', ''),
            'snippet': email.get('snippet', ''),
            'action': example.get('decision'),
            'features': {},
        })
    return reconstructed


def _session_account_id(preferences: dict) -> str | None:
    meta = preferences.get('metadata') or {}
    return meta.get('accountId')


def _swipe_account_id(swipe: dict, preferences: dict) -> str | None:
    return swipe.get('accountId') or _session_account_id(preferences)


def _attach_account(policy: dict, account_id: str | None) -> dict:
    if account_id:
        policy['accountId'] = account_id
    return policy


def _group_swipes_by_account(swipes: list[dict], preferences: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    session_aid = _session_account_id(preferences)
    for swipe in swipes:
        aid = _swipe_account_id(swipe, preferences) or session_aid or '_default'
        grouped[aid].append(swipe)
    return grouped


def _domain_account_id(
    swipes: list[dict],
    domain: str,
    preferences: dict,
    session_account: str | None,
) -> str | None:
    ids = {
        _swipe_account_id(s, preferences)
        for s in swipes
        if (s.get('features', {}).get('senderDomain') or extract_domain(s.get('from') or '')) == domain
        and _swipe_account_id(s, preferences)
    }
    ids.discard(None)
    if len(ids) == 1:
        return ids.pop()
    return session_account


def group_by_domain(swipes: list[dict]) -> dict[str, Counter]:
    domains: dict[str, Counter] = defaultdict(Counter)
    for swipe in swipes:
        action = swipe.get('action')
        if not action or action == 'skip':
            continue
        domain = swipe.get('features', {}).get('senderDomain') or extract_domain(
            swipe.get('from') or swipe.get('sender', '')
        )
        if domain:
            domains[domain][action] += 1
    return domains


def group_by_sender(swipes: list[dict]) -> dict[str, Counter]:
    senders: dict[str, Counter] = defaultdict(Counter)
    for swipe in swipes:
        action = swipe.get('action')
        if not action or action == 'skip':
            continue
        sender = swipe.get('from') or swipe.get('sender', '')
        if sender:
            senders[sender][action] += 1
    return senders


def dominant_action(counter: Counter, min_count: int = 3, min_ratio: float = 0.8):
    total = sum(counter.values())
    if total < min_count:
        return None, 0.0
    action, count = counter.most_common(1)[0]
    ratio = count / total
    if ratio < min_ratio:
        return None, ratio
    if len(counter) > 1 and counter.most_common(2)[1][1] >= 2:
        return None, ratio
    return action, ratio


def _normalize_action(action: str | None) -> str:
    if action in ('needs_attention',):
        return 'important'
    if action == 'spam':
        return 'dont_keep'
    return action or 'keep'


def build_folder_routing_policies(swipes: list[dict], settings: dict) -> list[dict]:
    """Learn folder routing from don't-keep swipes with folderRoute + user-defined routes."""
    policies = []
    route_counts: dict[str, dict] = {}

    for swipe in swipes:
        if swipe.get('action') != 'spam':
            continue
        fr = swipe.get('folderRoute')
        if not fr:
            continue
        name = fr.get('folderName', 'Unfiled')
        key = name.lower()
        if key not in route_counts:
            route_counts[key] = {'name': name, 'count': 0, 'matchTypes': Counter()}
        route_counts[key]['count'] += 1
        mt = fr.get('matchType', 'keyword')
        mv = fr.get('matchValue', '')
        route_counts[key]['matchTypes'][(mt, mv)] += 1

    for key, data in route_counts.items():
        policies.append({
            'id': f'folder-route-{key.replace(" ", "-")}',
            'type': 'folder_route',
            'match': {'folderName': data['name']},
            'action': 'route_to_folder',
            'autonomyLevel': DEFAULT_AUTONOMY,
            'confidence': min(0.95, 0.5 + data['count'] * 0.1),
            'evidenceCount': data['count'],
            'suggestOnly': True,
            'preservesInbox': True,
            'userConfirmed': False,
        })

    folders_cfg = settings.get('folders', {})
    if folders_cfg.get('advancedRoutingEnabled'):
        for route in folders_cfg.get('routes', []):
            if route.get('action'):
                continue
            match_type = route.get('matchType', 'keyword')
            intent_id = route.get('matchValue') if match_type == 'intent' else None
            intent_meta = INTENT_DEFINITIONS.get(intent_id or '', {})
            match_mode = route.get('matchMode') or (
                'ai' if match_type == 'descriptor' else 'smart' if match_type == 'intent' else 'strict'
            )
            policies.append({
                'id': f'user-route-{route.get("id", route.get("name", "x"))}',
                'type': 'folder_route_definition',
                'match': {
                    'folderName': route.get('name'),
                    'matchType': match_type,
                    'matchMode': match_mode,
                    'matchValue': route.get('matchValue'),
                    'intent': intent_id,
                    'aiRule': route.get('aiRule') or route.get('description', ''),
                    'description': route.get('description') or route.get('aiRule') or intent_meta.get('description', ''),
                },
                'action': 'route_to_folder',
                'autonomyLevel': DEFAULT_AUTONOMY,
                'confidence': 0.85,
                'evidenceCount': 0,
                'suggestOnly': True,
                'preservesInbox': True,
                'userConfirmed': True,
                'source': 'user_settings',
                'matchMode': match_mode,
                'requiresAgentJudgment': match_type == 'descriptor',
            })

    return policies[:20]


def build_policy_graph(
    preferences: dict,
    platform: dict,
    watchlist: dict,
    swipes: list[dict] | None = None,
    settings: dict | None = None,
) -> dict:
    swipes = swipes or normalize_swipes(preferences)
    settings = settings or preferences.get('settings', {})
    session_account = _session_account_id(preferences)
    policies = []
    relationships = []

    folder_policies = build_folder_routing_policies(swipes, settings)
    policies.extend(folder_policies)

    domains = group_by_domain(swipes)
    for domain, actions in sorted(domains.items(), key=lambda x: sum(x[1].values()), reverse=True):
        action, confidence = dominant_action(actions)
        if not action:
            continue
        norm = _normalize_action(action)
        email_ids = [
            s.get('emailId') for s in swipes
            if (s.get('features', {}).get('senderDomain') or extract_domain(s.get('from') or '')) == domain
            and _normalize_action(s.get('action')) == norm
        ][:3]
        policies.append(_attach_account({
            'id': f'domain-{domain.replace(".", "-")}-{norm}',
            'type': 'sender_domain',
            'match': {'domain': domain},
            'action': norm,
            'autonomyLevel': DEFAULT_AUTONOMY,
            'confidence': round(confidence, 2),
            'evidenceCount': sum(actions.values()),
            'exceptions': [],
            'sourceExamples': [eid for eid in email_ids if eid],
            'userConfirmed': False,
        }, _domain_account_id(swipes, domain, preferences, session_account)))

    senders = group_by_sender(swipes)
    for sender, actions in senders.items():
        action, confidence = dominant_action(actions, min_count=3, min_ratio=0.85)
        if action not in ('important', 'needs_attention'):
            continue
        relationships.append(_attach_account({
            'type': 'important_sender',
            'match': {'sender': sender},
            'reason': f'Marked important {actions.get("important", 0) + actions.get("needs_attention", 0)} time(s)',
            'autonomyLevel': DEFAULT_AUTONOMY,
            'confidence': round(confidence, 2),
        }, session_account))

    for swipe in swipes:
        text = f'{swipe.get("subject", "")} {swipe.get("snippet", "")}'.lower()
        if 'unsubscribe' in text or swipe.get('features', {}).get('isNewsletter'):
            domain = swipe.get('features', {}).get('senderDomain') or extract_domain(swipe.get('from') or '')
            if domain and not any(p['match'].get('domain') == domain for p in policies):
                action, confidence = dominant_action(
                    domains.get(domain, Counter()),
                    min_count=2,
                    min_ratio=0.7,
                )
                if action == 'spam':
                    policies.append({
                        'id': f'newsletter-{domain.replace(".", "-")}',
                        'type': 'newsletter_pattern',
                        'match': {'domain': domain, 'signal': 'newsletter'},
                        'action': 'dont_keep',
                        'autonomyLevel': DEFAULT_AUTONOMY,
                        'confidence': round(confidence, 2),
                        'evidenceCount': sum(domains.get(domain, Counter()).values()),
                        'exceptions': [],
                        'sourceExamples': [],
                        'userConfirmed': False,
                    })

    keyword_policies = []
    for kw in URGENT_KEYWORDS:
        keyword_policies.append({
            'id': f'urgent-{kw.replace(" ", "-")}',
            'type': 'keyword_watch',
            'match': {'subjectOrSnippetContains': kw},
            'action': 'surface_attention',
            'autonomyLevel': DEFAULT_AUTONOMY,
            'confidence': 0.7,
            'evidenceCount': 0,
            'exceptions': [],
            'sourceExamples': [],
            'userConfirmed': False,
        })

    training_gaps = []
    for item in watchlist.get('inconsistentSenders', [])[:10]:
        training_gaps.append({
            'gap': 'inconsistent_sender',
            'match': {'sender': item.get('sender')},
            'suggestedFollowUp': f'Swipe 3–5 more emails from {item.get("sender")} to clarify preference',
        })

    policy_candidates = []
    for domain, actions in domains.items():
        if len(actions) > 1 and sum(actions.values()) >= 2:
            policy_candidates.append({
                'match': {'domain': domain},
                'actions': dict(actions),
                'requiresReview': True,
                'reason': 'Mixed decisions — needs more training before a firm rule',
            })

    return {
        'version': '1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'unifiedInboxEnabled': is_unified_inbox_enabled(settings),
        'sessionAccountId': session_account,
        'accounts': accounts_for_policy_graph(settings),
        'policies': policies[:20],
        'relationships': relationships[:15],
        'keywordWatchPolicies': keyword_policies,
        'hardConstraints': list(HARD_CONSTRAINTS),
        'platformLabelCandidates': platform.get('suggestions', [])[:12],
        'trainingGaps': training_gaps,
        'policyCandidates': policy_candidates[:10],
        'folderRoutingPolicies': [p for p in policies if p.get('type', '').startswith('folder_route')],
        'autonomyLadder': [
            'recommend',
            'label',
            'draft',
            'move_with_approval',
            'narrow_auto_archive',
            'send_authorized_only',
        ],
        'defaultAutonomyLevel': resolve_autonomy_level(settings),
    }


def build_calibration(preferences: dict, swipes: list[dict] | None = None) -> dict:
    swipes = swipes or normalize_swipes(preferences)
    meta = preferences.get('metadata', {})
    agent_review = meta.get('agentReview', {})

    scorable = agent_review.get('scorablePredictions', 0)
    correct = agent_review.get('correctPredictions', 0)
    agreement = round(correct / scorable, 2) if scorable else None

    by_action: dict[str, dict] = {}
    misses = agent_review.get('misses', [])
    for action in ('spam', 'keep', 'important'):
        action_misses = [m for m in misses if m.get('actual') == action or (
            action == 'important' and m.get('actual') == 'needs_attention'
        )]
        action_swipes = [s for s in swipes if _normalize_action(s.get('action')) == _normalize_action(action)]
        total = len(action_swipes)
        miss_count = len(action_misses)
        if total > 0:
            by_action[action] = {
                'swipeCount': total,
                'missCount': miss_count,
                'agreement': round(1 - miss_count / total, 2) if total else None,
            }

    reversed_in_review = sum(
        1 for s in swipes
        if s.get('correctionNote') or s.get('reviewEdited')
    )

    inconsistent = []
    senders = group_by_sender(swipes)
    for sender, actions in senders.items():
        if len(actions) > 1 and sum(actions.values()) >= 3:
            inconsistent.append({
                'sender': sender,
                'actions': dict(actions),
            })

    return {
        'version': '1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'overall': {
            'scorable': scorable,
            'correct': correct,
            'agreement': agreement,
            'swipeCount': len(swipes),
        },
        'byAction': by_action,
        'inconsistentSenders': inconsistent[:10],
        'reversedInReview': reversed_in_review,
        'correctionNotes': sum(1 for s in swipes if s.get('correctionNote')),
    }


def build_assistant_brief(
    preferences: dict,
    policy_graph: dict,
    calibration: dict,
    watchlist: dict,
    settings: dict,
) -> str:
    swipes = normalize_swipes(preferences)
    count = len(swipes)
    agent_name = settings.get('agent', {}).get('name', '').strip() or 'your agent'
    session_account = _session_account_id(preferences)
    lines = [
        f'# What you taught {agent_name} ({count} emails)',
        '',
        f'Generated: {policy_graph.get("generatedAt", "")[:19]}',
        '',
    ]

    if session_account:
        label = account_label(settings, session_account) or session_account
        lines.append(f'*Training session mailbox:* **{label}** (`{session_account}`)')
        lines.append('')

    ui_enabled = is_unified_inbox_enabled(settings)
    registered = list_accounts(settings)
    by_account = _group_swipes_by_account(swipes, preferences)
    account_keys = [k for k in by_account if k != '_default']

    if ui_enabled and (registered or len(account_keys) > 1 or session_account):
        lines.append('## Across your inboxes')
        lines.append('')
        lines.append(
            'Unified inbox is on. Mail stays in your normal apps (Gmail, Apple Mail, Outlook). '
            'Your agent merges per-mailbox rules below and triages in chat — recommend-only unless you approve more.'
        )
        lines.append('')
        if registered:
            for acc in registered:
                aid = acc.get('id', '')
                label = acc.get('label', aid)
                trained = len(by_account.get(aid, []))
                status = f'{trained} swipe(s) in latest compile' if trained else 'not trained in this session yet'
                lines.append(f'- **{label}** (`{aid}`) — {status}')
        elif account_keys:
            for aid in account_keys:
                label = account_label(settings, aid) or aid
                lines.append(f'- **{label}** — {len(by_account[aid])} swipe(s) in this compile')
        lines.append('')

    ready = [p for p in policy_graph.get('policies', []) if p.get('confidence', 0) >= 0.75]
    if ready:
        lines.append('## Ready to recommend (not act)')
        lines.append('')
        dont_keep = [p for p in ready if p.get('action') == 'dont_keep']
        if dont_keep:
            domains = ', '.join(p['match'].get('domain', '?') for p in dont_keep[:6])
            lines.append(f"- Don't keep promotional or low-value mail from: **{domains}**")
        for rel in policy_graph.get('relationships', [])[:5]:
            sender = rel.get('match', {}).get('sender', '')
            lines.append(f"- Flag as important: **{sender}** — {rel.get('reason', '')}")
        urgent_kws = [p['match']['subjectOrSnippetContains'] for p in policy_graph.get('keywordWatchPolicies', [])[:5]]
        if urgent_kws:
            lines.append(f"- Surface urgent keywords: {', '.join(urgent_kws)}")
        lines.append('')

    folder_routes = policy_graph.get('folderRoutingPolicies', [])
    if folder_routes:
        lines.append('## Folder routing (suggest-only)')
        lines.append('')
        lines.append(
            'These are the user\'s advanced folder routes. Remember them across sessions '
            '(persisted in settings.json) and build them out in their email platform as '
            'labels/folders — inbox-preserving unless the user approves a skip-inbox filter.'
        )
        lines.append('')
        for fr in folder_routes[:8]:
            name = fr.get('match', {}).get('folderName', '?')
            intent = fr.get('match', {}).get('intent')
            mode = fr.get('match', {}).get('matchMode') or fr.get('matchMode', '')
            ai_rule = fr.get('match', {}).get('aiRule', '')
            desc = fr.get('match', {}).get('description', '')
            if mode == 'ai' and ai_rule:
                lines.append(f"- **{name}** — AI rule: {ai_rule[:80]}{'…' if len(ai_rule) > 80 else ''}")
            elif intent and intent in INTENT_DEFINITIONS:
                label = INTENT_DEFINITIONS[intent]['label']
                lines.append(f"- **{name}** — smart match: {label}")
            elif desc:
                lines.append(f"- **{name}** — {desc}")
            else:
                lines.append(f"- Route matching mail to **{name}** — inbox preserved until you approve")
        lines.append('')

    gaps = policy_graph.get('trainingGaps', [])
    if gaps:
        lines.append('## Needs more training')
        lines.append('')
        for gap in gaps[:8]:
            sender = gap.get('match', {}).get('sender', 'unknown sender')
            lines.append(f'- **{sender}** — inconsistent decisions during training')
        lines.append('')

    cal = calibration.get('overall', {})
    if cal.get('scorable'):
        lines.append('## Session calibration')
        lines.append('')
        pct = int((cal.get('agreement') or 0) * 100)
        lines.append(
            f"- {agent_name.title()} agreed with you on **{cal.get('correct', 0)} of {cal.get('scorable', 0)}** "
            f'scorable predictions ({pct}%)'
        )
        lines.append('')

    history = load_session_history()
    trend = compute_score_trend(history.get('sessions', []))
    if trend.get('status') != 'insufficient_data':
        lines.append('## Progress over time')
        lines.append('')
        latest_pct = int((trend.get('latestAgreement') or 0) * 100)
        prev_pct = int((trend.get('previousAgreement') or 0) * 100)
        delta = int(round((trend.get('delta') or 0) * 100))
        delta_label = f'+{delta}' if delta > 0 else str(delta)
        lines.append(
            f"- **{trend.get('headline', 'Progress')}** — {trend.get('message', '')} "
            f'Latest scored session: **{latest_pct}%** vs **{prev_pct}%** before ({delta_label} pts).'
        )
        if trend.get('needsAttention'):
            lines.append('- Recommendation: run a short refine session on the agent misses before trusting new rules.')
        lines.append('')

    lines.extend([
        '## Autonomy today',
        '',
        '- **Recommend only.** No labels, archive, or send without your approval.',
        '- Platform label ideas are suggestions — inbox visibility is preserved.',
        '',
        '## Next step',
        '',
        f'{agent_name.title()} should use these rules in **recommendation mode** for new mail.',
        'Review this brief together, confirm or adjust policies, then begin inbox review.',
        '',
    ])

    return '\n'.join(lines)


def write_policy_artifacts(
    output_dir: Path,
    policy_graph: dict,
    calibration: dict,
    brief: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    graph_path = output_dir / 'policy-graph.json'
    with open(graph_path, 'w') as f:
        json.dump(policy_graph, f, indent=2)
        f.write('\n')
    paths['policyGraph'] = str(graph_path)

    cal_path = output_dir / 'calibration.json'
    with open(cal_path, 'w') as f:
        json.dump(calibration, f, indent=2)
        f.write('\n')
    paths['calibration'] = str(cal_path)

    brief_path = output_dir / 'assistant-brief.md'
    brief_path.write_text(brief)
    paths['policyBrief'] = str(brief_path)

    return paths
