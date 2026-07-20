#!/usr/bin/env python3
"""Seed policy-graph.json from imported user rules (calibrate path)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from policy_compiler import DEFAULT_AUTONOMY, HARD_CONSTRAINTS, write_policy_artifacts
from settings import USER_DIR

POLICY_GRAPH = USER_DIR / 'policy-graph.json'


def _slug(value: str) -> str:
    return value.lower().replace('@', '-at-').replace('.', '-').replace(' ', '-')[:48]


def policy_from_import(item: dict, index: int) -> dict:
    match = item.get('match', {})
    action = item.get('action', 'dont_keep')
    if action == 'spam':
        action = 'dont_keep'
    domain = match.get('domain', '')
    sender = match.get('sender', '')
    key = domain or sender or f'rule-{index}'
    return {
        'id': item.get('id') or f'imported-{_slug(key)}-{action}',
        'type': item.get('type', 'sender_domain' if domain else 'sender'),
        'match': match,
        'action': action,
        'autonomyLevel': item.get('autonomyLevel', DEFAULT_AUTONOMY),
        'confidence': item.get('confidence', 0.9),
        'evidenceCount': 0,
        'exceptions': item.get('exceptions', []),
        'sourceExamples': [],
        'userConfirmed': True,
        'source': 'imported',
        'reason': item.get('reason', 'Imported from user rules'),
    }


def relationship_from_import(item: dict, index: int) -> dict:
    match = item.get('match', {})
    sender = match.get('sender', '')
    return {
        'type': item.get('type', 'important_sender'),
        'match': match,
        'reason': item.get('reason', f'Imported important sender: {sender}'),
        'autonomyLevel': item.get('autonomyLevel', DEFAULT_AUTONOMY),
        'confidence': item.get('confidence', 0.9),
        'source': 'imported',
        'userConfirmed': True,
    }


def seed_policy_graph(rules: dict, output_dir: Path | None = None) -> dict:
    output_dir = output_dir or USER_DIR
    policies = [policy_from_import(p, i) for i, p in enumerate(rules.get('policies', []))]
    relationships = [
        relationship_from_import(r, i) for i, r in enumerate(rules.get('relationships', []))
    ]

    existing = {}
    if POLICY_GRAPH.exists():
        with open(POLICY_GRAPH) as f:
            existing = json.load(f)

    graph = {
        'version': '1.0',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'imported_rules',
        'policies': policies + [
            p for p in existing.get('policies', [])
            if p.get('source') != 'imported'
        ][:10],
        'relationships': relationships + existing.get('relationships', [])[:5],
        'keywordWatchPolicies': existing.get('keywordWatchPolicies', []),
        'hardConstraints': list(HARD_CONSTRAINTS),
        'platformLabelCandidates': existing.get('platformLabelCandidates', []),
        'trainingGaps': existing.get('trainingGaps', []),
        'policyCandidates': existing.get('policyCandidates', []),
        'autonomyLadder': existing.get('autonomyLadder', [
            'recommend', 'label', 'draft', 'move_with_approval',
            'narrow_auto_archive', 'send_authorized_only',
        ]),
        'defaultAutonomyLevel': DEFAULT_AUTONOMY,
        'importedRuleCount': len(policies) + len(relationships),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / 'policy-graph.json', 'w') as f:
        json.dump(graph, f, indent=2)
        f.write('\n')

    brief = _import_brief(graph, rules)
    cal = existing.get('calibration') or {
        'version': '1.0',
        'generatedAt': graph['generatedAt'],
        'overall': {'scorable': 0, 'correct': 0, 'agreement': None, 'swipeCount': 0},
        'byAction': {},
        'inconsistentSenders': [],
        'reversedInReview': 0,
        'correctionNotes': 0,
    }
    if isinstance(cal, dict) and 'version' not in cal:
        cal = {
            'version': '1.0',
            'generatedAt': graph['generatedAt'],
            'overall': {'scorable': 0, 'correct': 0, 'agreement': None, 'swipeCount': 0},
            'byAction': {},
            'inconsistentSenders': [],
            'reversedInReview': 0,
            'correctionNotes': 0,
        }

    paths = write_policy_artifacts(output_dir, graph, cal, brief)
    return {'ok': True, 'policyGraph': str(output_dir / 'policy-graph.json'), **paths}


def _import_brief(graph: dict, rules: dict) -> str:
    n = graph.get('importedRuleCount', 0)
    lines = [
        f'# Imported rules ({n} items)',
        '',
        f'Generated: {graph.get("generatedAt", "")[:19]}',
        '',
        '## Imported (user confirmed)',
        '',
    ]
    for p in graph.get('policies', [])[:15]:
        if p.get('source') == 'imported':
            m = p.get('match', {})
            target = m.get('domain') or m.get('sender', '?')
            lines.append(f"- **{target}** → {p.get('action')} — {p.get('reason', '')}")
    for r in graph.get('relationships', [])[:10]:
        if r.get('source') == 'imported':
            sender = r.get('match', {}).get('sender', '?')
            lines.append(f"- **{sender}** → important — {r.get('reason', '')}")

    lines.extend([
        '',
        '## Next step',
        '',
        'Run a **calibrate** swipe session on emails where confidence is low.',
        'Autonomy: **recommend only** until you approve more.',
        '',
    ])
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Seed policy-graph from imported rules')
    parser.add_argument('rules', nargs='?', help='JSON file with policies + relationships')
    parser.add_argument('--output-dir', '-o', default=str(USER_DIR))
    args = parser.parse_args()

    if args.rules:
        with open(args.rules) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    result = seed_policy_graph(data, Path(args.output_dir))
    print(json.dumps(result, indent=2))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
