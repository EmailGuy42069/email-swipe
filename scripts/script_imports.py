"""Load hyphenated script modules from scripts/."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    path = _SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyze_preferences_mod = load_module('analyze_preferences', 'analyze-preferences.py')
session_intake_mod = load_module('session_intake', 'session-intake.py')
