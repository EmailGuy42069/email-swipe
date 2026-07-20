#!/usr/bin/env python3
"""Optional: enable agent inbox review after training."""
import sys

from settings import DEFAULT_SETTINGS, SETTINGS_FILE, load_settings, save_settings, settings_status


def prompt_bool(label, default=False):
    default_str = 'Y/n' if default else 'y/N'
    value = input(f'{label} ({default_str}): ').strip().lower()
    if not value:
        return default
    return value in ('y', 'yes', '1', 'true')


def main():
    print('=== Email Swipe — Agent Setup ===\n')
    print('Optional. Most users skip this and start swiping.\n')

    settings = load_settings() if SETTINGS_FILE.exists() else deepcopy_defaults()
    settings['agent']['enabled'] = prompt_bool(
        'Let your agent review inbox after training?', settings['agent'].get('enabled', False)
    )

    path = save_settings(settings)
    status = settings_status(settings)
    print(f'\nSaved {path}')
    print(f'  Agent review: {"on" if status["agentEnabled"] else "off"}')
    print('\nYour agent can collect job context and goals in chat.')
    return 0


def deepcopy_defaults():
    import copy
    return copy.deepcopy(DEFAULT_SETTINGS)


if __name__ == '__main__':
    sys.exit(main())
