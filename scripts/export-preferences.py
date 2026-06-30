#!/usr/bin/env python3
"""Convert IndexedDB export to agent-readable format"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path.home() / '.config' / 'email-swipe'
OUTPUT_FILE = CONFIG_DIR / 'preferences.json'


def extract_sender_domain(sender: str) -> str:
    if '@' in sender:
        return sender.split('@', 1)[1]
    return ''


def extract_patterns(by_action: dict) -> dict:
    patterns = {
        'alwaysKeep': [],
        'alwaysSpam': [],
        'alwaysImportant': [],
        'alwaysArchive': [],
        'alwaysUnsubscribe': [],
        'alwaysBlock': [],
    }
    action_map = {
        'keep': 'alwaysKeep',
        'spam': 'alwaysSpam',
        'important': 'alwaysImportant',
        'archive': 'alwaysArchive',
        'unsubscribe': 'alwaysUnsubscribe',
        'block': 'alwaysBlock',
    }

    for action, key in action_map.items():
        items = by_action.get(action, [])
        domain_counts: Counter = Counter()
        keyword_counts: Counter = Counter()

        for swipe in items:
            features = swipe.get('features', {})
            domain = features.get('senderDomain') or extract_sender_domain(
                swipe.get('from', swipe.get('sender', ''))
            )
            if domain:
                domain_counts[domain] += 1
            for kw in features.get('keywords', []):
                keyword_counts[kw] += 1

        for domain, count in domain_counts.most_common(5):
            if count >= 2:
                patterns[key].append(f'Emails from {domain} ({count}x)')

        for kw, count in keyword_counts.most_common(3):
            if count >= 2:
                patterns[key].append(f'Contains "{kw}" ({count}x)')

    return patterns


def generate_few_shot_examples(swipes: list) -> list:
    examples = []
    seen = set()

    for swipe in swipes:
        key = f"{swipe.get('sender')}-{swipe.get('action')}"
        if key in seen:
            continue
        seen.add(key)

        features = swipe.get('features', {})
        parts = []
        if features.get('isNewsletter'):
            parts.append('newsletter')
        if features.get('hasAttachment'):
            parts.append('has attachment')
        if features.get('senderDomain'):
            parts.append(f"from {features['senderDomain']}")
        if features.get('keywords'):
            parts.append(f"keywords: {', '.join(features['keywords'])}")

        examples.append({
            'email': {
                'subject': swipe.get('subject', ''),
                'sender': swipe.get('sender', ''),
                'snippet': swipe.get('snippet', ''),
            },
            'decision': swipe.get('action'),
            'reasoning': f"{swipe.get('action')} — {', '.join(parts) if parts else 'user preference'}",
        })

        if len(examples) >= 10:
            break

    return examples


def extract_sender_rules(swipes: list) -> dict:
    sender_actions: dict = {}

    for swipe in swipes:
        action = swipe.get('action')
        if action == 'skip':
            continue
        sender = swipe.get('from') or swipe.get('sender', '')
        if sender not in sender_actions:
            sender_actions[sender] = Counter()
        sender_actions[sender][action] += 1

    rules = {}
    for sender, actions in sender_actions.items():
        top_action, count = actions.most_common(1)[0]
        if count >= 1:
            rules[sender] = top_action

    return rules


def process_swipes(swipe_data: list) -> dict:
    by_action = {'keep': [], 'spam': [], 'archive': [], 'important': [], 'unsubscribe': [], 'block': []}
    for swipe in swipe_data:
        action = swipe.get('action')
        if action in by_action:
            by_action[action].append(swipe)

    return {
        'metadata': {
            'generatedAt': datetime.now().isoformat(),
            'totalSwipes': len(swipe_data),
            'version': '1.1',
        },
        'patterns': extract_patterns(by_action),
        'fewShotExamples': generate_few_shot_examples(swipe_data),
        'senderRules': extract_sender_rules(swipe_data),
        'folderRules': extract_folder_rules(swipe_data),
    }


def extract_folder_rules(swipes: list) -> dict:
    folder_actions = {'archive', 'important', 'unsubscribe', 'block'}
    rules = {}
    for swipe in swipes:
        action = swipe.get('action')
        if action not in folder_actions:
            continue
        sender = swipe.get('from') or swipe.get('sender', '')
        rules[sender] = action
    return rules


def main():
    if len(sys.argv) < 2:
        print('Usage: export-preferences.py <swipe-export.json>')
        print('  Reads browser-exported swipe data and writes to ~/.config/email-swipe/preferences.json')
        sys.exit(1)

    input_path = Path(sys.argv[1])
    with open(input_path) as f:
        swipe_data = json.load(f)

    preferences = process_swipes(swipe_data)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(preferences, f, indent=2)

    print(f'Wrote {OUTPUT_FILE} ({preferences["metadata"]["totalSwipes"]} swipes)')


if __name__ == '__main__':
    main()
