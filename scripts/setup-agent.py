#!/usr/bin/env python3
"""Write assets/ui/settings.json so the swipe UI can show the agent's name."""

import json
import os
import sys
from pathlib import Path

AGENT_NAME = os.environ.get('AGENT_NAME', 'Agent')
SETTINGS_PATH = Path(__file__).resolve().parent.parent / 'assets' / 'ui' / 'settings.json'


def main() -> int:
    settings = {
        'version': '2.0',
        'agent': {
            'enabled': True,
            'name': AGENT_NAME,
        },
    }

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')

    print(f'Agent identity set: {AGENT_NAME}')
    print(f'Settings written to: {SETTINGS_PATH}')
    print('\nThe UI will now show:')
    print(f'  - "Perfect score, {AGENT_NAME}"')
    print(f'  - "{AGENT_NAME} missed on these guesses"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
