#!/usr/bin/env python3
"""
Analyze swipe training + settings into intermediate compile outputs.

Prefer `compile_training.py` for the full pipeline (policy graph, brief, calibration).
This module is used internally by compile_training; the CLI is for debugging only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from settings import (
    SETTINGS_FILE,
    USER_DIR,
    _deep_merge,
    folder_budget,
    load_settings,
    save_settings,
)

URGENT_KEYWORDS = (
    'urgent', 'action required', 'deadline', 'expires', 'overdue',
    'security alert', 'verify your account', 'payment failed', 'past due',
    'respond by', 'time sensitive', 'immediate attention',
)

SAFE_PLATFORM_ACTIONS = {
    'spam': {'suggestedAction': 'label', 'labelName': 'Likely Spam (review)', 'reason': 'Repeated spam swipes'},
    'keep': {'suggestedAction': 'label', 'labelName': 'Priority', 'reason': 'Consistently kept'},
}
# needs_attention → agent watchlist only, never a platform filter


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


def build_folder_route_rules(settings: dict) -> list[dict]:
    """Translate user-defined advanced folder routes into platform-rule suggestions.

    These describe labels/folders the agent should build out in the email platform.
    They stay suggest-only and inbox-preserving unless the user approves otherwise.
    """
    folders_cfg = settings.get('folders', {})
    if not folders_cfg.get('advancedRoutingEnabled'):
        return []

    never_remove = settings.get('platformRules', {}).get('neverRemoveFromInbox', True)
    rules = []
    for route in folders_cfg.get('routes', []):
        # Inbox-action routes (keep/important/spam) are training signals, not folders.
        if route.get('action'):
            continue
        name = (route.get('name') or '').strip()
        if not name:
            continue

        match_type = route.get('matchType', 'descriptor')
        match_mode = route.get('matchMode') or (
            'ai' if match_type == 'descriptor' else 'smart' if match_type == 'intent' else 'strict'
        )
        requires_judgment = match_type == 'descriptor'
        ai_rule = route.get('aiRule') or route.get('description') or None

        rules.append({
            'id': f'folder-route-{re.sub(r"[^a-z0-9]+", "-", name.lower())[:40]}',
            'folderName': name,
            'labelName': name,
            'suggestedAction': 'label',
            'match': {
                'type': match_type,
                'mode': match_mode,
                'value': route.get('matchValue') or None,
                'intent': route.get('matchValue') if match_type == 'intent' else None,
                'aiRule': ai_rule,
            },
            'reason': 'User-defined folder route (advanced settings)',
            'howToBuild': (
                'Create a label/folder named "%s" and route matching mail to it. '
                'Keep it visible in the inbox unless the user approves a skip-inbox filter.'
                % name
            ),
            'preservesInbox': never_remove,
            'requiresUserConfirmation': True,
            'requiresAgentJudgment': requires_judgment,
            'autoApply': False,
            'source': 'user_settings',
        })
    return rules


def build_platform_rules(swipes: list[dict], settings: dict) -> dict:
    platform_cfg = settings.get('platformRules', {})
    mode = platform_cfg.get('mode', 'suggest_only')
    max_rules = platform_cfg.get('maxSuggestedRules', 12)
    never_remove = platform_cfg.get('neverRemoveFromInbox', True)

    # Mail filed to a folder (has folderRoute) is handled by folderRoutes below —
    # exclude it here so a "Receipts" domain isn't mislabeled "Likely Spam".
    label_swipes = [s for s in swipes if not s.get('folderRoute')]

    suggestions = []
    domains = group_by_domain(label_swipes)

    for domain, actions in sorted(domains.items(), key=lambda x: sum(x[1].values()), reverse=True):
        action, confidence = dominant_action(actions)
        if not action or action not in SAFE_PLATFORM_ACTIONS:
            continue
        if action == 'block':
            continue

        template = SAFE_PLATFORM_ACTIONS[action]
        suggestions.append({
            'id': f'domain-{domain.replace(".", "-")}',
            'match': {'type': 'domain', 'value': domain},
            'suggestedAction': template['suggestedAction'],
            'labelName': template['labelName'],
            'reason': template['reason'],
            'confidence': round(confidence, 2),
            'evidence': {'swipeCount': sum(actions.values()), 'action': action},
            'preservesInbox': never_remove,
            'requiresUserConfirmation': True,
            'autoApply': False,
            'warnings': [
                'Future mail from this domain still arrives in the inbox unless you explicitly create a skip-inbox filter.',
            ],
        })

    senders = group_by_sender(label_swipes)
    for sender, actions in senders.items():
        action, confidence = dominant_action(actions, min_count=4, min_ratio=0.9)
        if not action or action not in SAFE_PLATFORM_ACTIONS or action == 'block':
            continue
        domain = extract_domain(sender)
        if any(s['match'].get('value') == domain for s in suggestions if s['match']['type'] == 'domain'):
            continue

        template = SAFE_PLATFORM_ACTIONS[action]
        suggestions.append({
            'id': f'sender-{re.sub(r"[^a-z0-9]+", "-", sender.lower())[:40]}',
            'match': {'type': 'sender', 'value': sender},
            'suggestedAction': template['suggestedAction'],
            'labelName': template['labelName'],
            'reason': f'Strong sender pattern ({action})',
            'confidence': round(confidence, 2),
            'evidence': {'swipeCount': sum(actions.values()), 'action': action},
            'preservesInbox': never_remove,
            'requiresUserConfirmation': True,
            'autoApply': False,
        })

    folder_routes = build_folder_route_rules(settings)

    return {
        'version': '1.1',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'mode': mode,
        'policy': {
            'neverRemoveFromInbox': never_remove,
            'allowedActions': platform_cfg.get('allowedActions', ['label', 'star']),
            'forbiddenActions': platform_cfg.get('forbiddenActions', []),
            'note': (
                'These are suggestions only. Labels and stars do not hide mail from the inbox. '
                'Do not create skip-inbox or auto-archive filters without explicit user approval.'
            ),
        },
        'suggestions': suggestions[:max_rules],
        'folderRoutes': folder_routes,
        'advancedRoutingEnabled': settings.get('folders', {}).get('advancedRoutingEnabled', False),
    }


def build_folder_suggestions(swipes: list[dict], settings: dict) -> dict:
    folders_cfg = settings.get('folders', {})
    preference = folders_cfg.get('preference', 'minimal')
    budget = folder_budget(preference)
    urgent_name = folders_cfg.get('urgentFolderName', 'Needs Attention')

    suggestions = []

    if folders_cfg.get('includeUrgentFolder', True):
        suggestions.append({
            'name': urgent_name,
            'type': 'agent_managed',
            'reason': 'Agent-curated folder for mail that needs your attention (not auto-filtered)',
            'confidence': 1.0,
            'preservesInbox': True,
            'implementation': 'agent_watchlist',
        })

    domain_actions = group_by_domain(swipes)
    keyword_buckets = Counter()
    for swipe in swipes:
        for kw in swipe.get('features', {}).get('keywords', []):
            keyword_buckets[kw] += 1

    candidates = []
    folder_templates = {
        'receipt': ('Receipts', 'Receipt / payment emails'),
        'newsletter': ('Newsletters', 'Newsletter and digest pattern'),
        'digest': ('Newsletters', 'Digest emails'),
        'promo': ('Promotions', 'Promotional mail'),
        'unsubscribe': ('Newsletters', 'List mail with unsubscribe headers'),
    }

    for kw, count in keyword_buckets.most_common():
        if count < 2 or kw not in folder_templates:
            continue
        name, reason = folder_templates[kw]
        candidates.append({
            'name': name,
            'type': 'user_folder',
            'reason': reason,
            'confidence': min(0.95, 0.5 + count * 0.1),
            'preservesInbox': True,
            'implementation': 'platform_label',
        })

    for domain, actions in domain_actions.items():
        action, confidence = dominant_action(actions, min_count=3, min_ratio=0.75)
        if action == 'archive':
            candidates.append({
                'name': f'{domain.split(".")[0].title()} Archive',
                'type': 'user_folder',
                'reason': f'You often archive mail from {domain}',
                'confidence': round(confidence, 2),
                'preservesInbox': True,
                'implementation': 'platform_label',
                'match': {'domain': domain},
            })
        elif action == 'keep' and confidence >= 0.85:
            candidates.append({
                'name': f'{domain.split(".")[0].title()} Priority',
                'type': 'user_folder',
                'reason': f'You consistently keep mail from {domain}',
                'confidence': round(confidence, 2),
                'preservesInbox': True,
                'implementation': 'platform_label',
                'match': {'domain': domain},
            })

    seen_names = {s['name'] for s in suggestions}
    for candidate in sorted(candidates, key=lambda x: x['confidence'], reverse=True):
        if candidate['name'] in seen_names:
            continue
        suggestions.append(candidate)
        seen_names.add(candidate['name'])
        if len([s for s in suggestions if s['type'] == 'user_folder']) >= budget:
            break

    return {
        'version': '1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'folderPreference': preference,
        'suggestions': suggestions,
    }


def build_agent_watchlist(swipes: list[dict], settings: dict) -> dict:
    agent_cfg = settings.get('agent', {})
    folders_cfg = settings.get('folders', {})
    context = settings.get('context', {})
    urgent_name = folders_cfg.get('urgentFolderName', 'Needs Attention')

    watch_rules = []
    inconsistent = []

    senders = group_by_sender(swipes)
    for sender, actions in senders.items():
        if len(actions) > 1 and sum(actions.values()) >= 3:
            inconsistent.append({
                'sender': sender,
                'actions': dict(actions),
                'reason': 'Mixed decisions during training — agent should review, not auto-rule',
            })

    for kw in URGENT_KEYWORDS:
        watch_rules.append({
            'id': f'urgent-keyword-{kw.replace(" ", "-")}',
            'priority': 'high',
            'folder': urgent_name,
            'trigger': {'subjectOrSnippetContains': kw},
            'instruction': (
                f'Surface in "{urgent_name}". Summarize why it may need attention and '
                'include deadline or action if present.'
            ),
            'requiresReasoning': True,
        })

    for swipe in swipes:
        action = swipe.get('action')
        if action in ('needs_attention', 'important'):
            sender = swipe.get('from') or swipe.get('sender', '')
            subject = swipe.get('subject', '')
            label = 'important' if action == 'important' else 'needs attention'
            watch_rules.append({
                'id': f'important-{re.sub(r"[^a-z0-9]+", "-", (sender or subject).lower())[:30]}',
                'priority': 'high',
                'folder': urgent_name,
                'trigger': {
                    'sender': sender,
                    'subjectContains': _extract_attention_keywords(subject, swipe.get('snippet', '')),
                },
                'instruction': f'User marked similar mail as {label} during training. Surface and summarize action items.',
                'requiresReasoning': True,
                'confidence': 0.85,
            })
    if context.get('problemToSolve', '').strip():
        watch_rules.append({
            'id': 'user-stated-problem',
            'priority': 'medium',
            'folder': urgent_name,
            'trigger': {'useContext': True},
            'instruction': (
                'User goal: '
                + context['problemToSolve'].strip()
                + '. Prefer surfacing mail that relates to this problem over bulk newsletter noise.'
            ),
            'requiresReasoning': True,
        })

    for item in inconsistent[:5]:
        watch_rules.append({
            'id': f'inconsistent-{re.sub(r"[^a-z0-9]+", "-", item["sender"].lower())[:30]}',
            'priority': 'low',
            'folder': urgent_name,
            'trigger': {'sender': item['sender']},
            'instruction': 'User was inconsistent on this sender. Ask for a quick decision if confidence is low.',
            'requiresReasoning': True,
            'evidence': item,
        })

    return {
        'version': '1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'agentEnabled': agent_cfg.get('enabled', False),
        'scanFrequency': agent_cfg.get('scanFrequency', 'twice_daily'),
        'needsAttentionFolder': {
            'name': urgent_name,
            'description': 'Agent-populated. Mail here still exists in the inbox unless the user moves it.',
            'populatedBy': 'agent_only',
        },
        'userContext': {
            'job': context.get('job', ''),
            'life': context.get('life', ''),
            'problemToSolve': context.get('problemToSolve', ''),
            'notes': context.get('notes', ''),
        },
        'watchRules': watch_rules,
        'inconsistentSenders': inconsistent,
        'runtimeGuidance': {
            'tokenBudget': 'Fetch metadata only; classify locally when possible; LLM only for watchlist matches.',
            'neverAutoDelete': True,
            'neverSkipInboxWithoutApproval': True,
        },
    }


def _extract_attention_keywords(subject: str, snippet: str) -> list[str]:
    text = f'{subject} {snippet}'.lower()
    found = [kw for kw in URGENT_KEYWORDS if kw in text]
    return found[:3] if found else []


def select_diverse_examples(swipes: list[dict], max_examples: int = 12) -> list[dict]:
    """Pick diverse few-shot examples — no fabricated reasoning."""
    seen_keys = set()
    examples = []
    priority_actions = ('important', 'needs_attention', 'keep', 'spam')

    for action in priority_actions:
        for swipe in swipes:
            if swipe.get('action') != action:
                continue
            key = f"{swipe.get('from')}-{action}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ex = {
                'email': {
                    'subject': swipe.get('subject', ''),
                    'sender': swipe.get('sender', ''),
                    'snippet': swipe.get('snippet', ''),
                    'from': swipe.get('from', ''),
                },
                'decision': action,
            }
            if swipe.get('correctionNote'):
                ex['userCorrection'] = swipe['correctionNote']
            if swipe.get('predictedAction'):
                ex['agentGuessed'] = swipe['predictedAction']
            examples.append(ex)
            if len(examples) >= max_examples:
                return examples

    for swipe in swipes:
        key = f"{swipe.get('from')}-{swipe.get('action')}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ex = {
            'email': {
                'subject': swipe.get('subject', ''),
                'sender': swipe.get('sender', ''),
                'snippet': swipe.get('snippet', ''),
                'from': swipe.get('from', ''),
            },
            'decision': swipe.get('action'),
        }
        if swipe.get('correctionNote'):
            ex['userCorrection'] = swipe['correctionNote']
        if swipe.get('predictedAction'):
            ex['agentGuessed'] = swipe['predictedAction']
        examples.append(ex)
        if len(examples) >= max_examples:
            break
    return examples


def build_training_pack(
    preferences: dict,
    settings: dict,
    folders: dict,
    platform: dict,
    watchlist: dict,
    summary: dict,
    artifact_refs: dict | None = None,
) -> dict:
    """Slim runtime slice — full policies live in policy-graph.json."""
    swipes = normalize_swipes(preferences)
    refs = artifact_refs or {}
    return {
        'version': '3.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'swipeCount': len(swipes),
        'summary': summary.get('headline', ''),
        'defaultAutonomyLevel': 'recommend',
        'artifactRefs': {
            'policyGraph': refs.get('policyGraph'),
            'policyBrief': refs.get('policyBrief'),
            'calibration': refs.get('calibration'),
        },
        'settings': {
            'agent': settings.get('agent', {}),
            'context': settings.get('context', {}),
        },
        'examples': select_diverse_examples(swipes, max_examples=8),
        'platformCandidates': platform.get('suggestions', [])[:6],
        'folderRoutes': platform.get('folderRoutes', []),
        'advancedRoutingEnabled': settings.get('folders', {}).get('advancedRoutingEnabled', False),
        'folderSuggestions': folders.get('suggestions', [])[:4],
        'watchRules': watchlist.get('watchRules', [])[:15],
        'needsAttentionFolder': watchlist.get('needsAttentionFolder', {}),
        'inconsistentSenders': watchlist.get('inconsistentSenders', [])[:5],
        'runtimeGuidance': watchlist.get('runtimeGuidance', {}),
    }


def build_summary(
    preferences: dict,
    settings: dict,
    folders: dict,
    platform: dict,
    watchlist: dict,
) -> dict:
    total = preferences.get('metadata', {}).get('totalSwipes', len(normalize_swipes(preferences)))
    return {
        'version': '1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'trainingSwipes': total,
        'settings': {
            'agentEnabled': settings.get('agent', {}).get('enabled', False),
            'folderPreference': settings.get('folders', {}).get('preference', 'minimal'),
            'platformRulesMode': settings.get('platformRules', {}).get('mode', 'suggest_only'),
        },
        'headline': (
            f'{len(platform.get("suggestions", []))} label suggestions, '
            f'{len(folders.get("suggestions", []))} folder ideas, '
            f'{len(watchlist.get("watchRules", []))} agent watch rules'
        ),
        'nextSteps': [
            'Read assistant-brief.md with the user — cement policies before inbox review.',
            'Use training-pack.json + policy-graph.json at runtime (recommend-only).',
            'Review platform label suggestions (inbox preserved) with user.',
        ],
        'cautions': [
            'Do not auto-apply filters that skip inbox or archive on arrival.',
            'Needs Attention is agent-managed, not a hard filter.',
            'Re-run analyze-preferences.py after additional training swipes.',
        ],
    }


def analyze_preferences(preferences: dict, settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    if preferences.get('settings'):
        settings = _deep_merge(settings, preferences['settings'])

    swipes = normalize_swipes(preferences)
    folders = build_folder_suggestions(swipes, settings)
    platform = build_platform_rules(swipes, settings)
    watchlist = build_agent_watchlist(swipes, settings)
    summary = build_summary(preferences, settings, folders, platform, watchlist)
    training_pack = build_training_pack(preferences, settings, folders, platform, watchlist, summary)

    return {
        'trainingPack': training_pack,
        'folderSuggestions': folders,
        'platformRules': platform,
        'agentWatchlist': watchlist,
        'analysisSummary': summary,
    }


def write_outputs(outputs: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        'training-pack.json': outputs['trainingPack'],
        'folder-suggestions.json': outputs['folderSuggestions'],
        'platform-rules.json': outputs['platformRules'],
        'agent-watchlist.json': outputs['agentWatchlist'],
        'analysis-summary.json': outputs['analysisSummary'],
    }
    for filename, data in mapping.items():
        path = output_dir / filename
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')


def main():
    parser = argparse.ArgumentParser(
        description='Debug/analyze preferences (prefer compile_training.py for full compile)',
    )
    parser.add_argument('preferences', nargs='?', help='Path to preferences.json (default: ~/.config/email-swipe/preferences.json)')
    parser.add_argument('--settings', help='Path to settings.json (default: ~/.config/email-swipe/settings.json)')
    parser.add_argument('--output-dir', '-o', help='Output directory (default: ~/.config/email-swipe/)')
    parser.add_argument('--save-settings', action='store_true', help='Persist settings embedded in preferences export')
    args = parser.parse_args()

    prefs_path = Path(args.preferences) if args.preferences else USER_DIR / 'preferences.json'
    if not prefs_path.exists():
        print(f'Error: preferences not found: {prefs_path}', file=sys.stderr)
        print('Export from the UI first, then import-preferences.py', file=sys.stderr)
        return 1

    with open(prefs_path) as f:
        preferences = json.load(f)

    settings_path = Path(args.settings) if args.settings else SETTINGS_FILE
    settings = load_settings(settings_path if settings_path.exists() else None)

    if preferences.get('settings'):
        settings = _deep_merge(settings, preferences['settings'])
        if args.save_settings:
            save_settings(settings)

    outputs = analyze_preferences(preferences, settings)
    output_dir = Path(args.output_dir) if args.output_dir else USER_DIR

    from script_imports import analyze_preferences_mod as _ap
    from compile_training import compile_training as run_compile

    result = run_compile(prefs_path, output_dir, save_settings_from_prefs=args.save_settings)
    if not result.get('ok'):
        print(result.get('error', 'compile failed'), file=sys.stderr)
        return 1

    with open(output_dir / 'analysis-summary.json') as f:
        summary = json.load(f)
    print(json.dumps(summary, indent=2))
    print(f'\nWrote outputs to {output_dir}/', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
