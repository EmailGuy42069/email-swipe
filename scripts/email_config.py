#!/usr/bin/env python3
"""Shared configuration for email-swipe scripts. No hardcoded accounts or paths."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = SKILL_ROOT / 'assets' / 'ui'
USER_CONFIG_DIR = Path.home() / '.config' / 'email-swipe'
USER_CONFIG_FILE = USER_CONFIG_DIR / 'config.json'
PROJECT_CONFIG_FILE = UI_DIR / 'config.json'


class ConfigError(Exception):
    """Raised when required configuration is missing."""


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_config() -> dict:
    """Merge config: user config → project config → env overrides."""
    cfg = {}

    if USER_CONFIG_FILE.exists():
        cfg.update(_load_json_file(USER_CONFIG_FILE))

    if PROJECT_CONFIG_FILE.exists():
        project = _load_json_file(PROJECT_CONFIG_FILE)
        # Only merge account-related keys from project config, not UI folders
        for key in ('email', 'gogPath', 'gmailServiceAccountFile', 'imap', 'provider'):
            if key in project:
                cfg[key] = project[key]

    if cfg.get('email') in (None, '', 'you@example.com') and not os.environ.get('EMAIL_SWIPE_EMAIL'):
        cfg.pop('email', None)
    if os.environ.get('EMAIL_SWIPE_EMAIL'):
        cfg['email'] = os.environ['EMAIL_SWIPE_EMAIL']
    if os.environ.get('EMAIL_SWIPE_GOG_PATH') or os.environ.get('GOG_PATH'):
        cfg['gogPath'] = os.environ.get('EMAIL_SWIPE_GOG_PATH') or os.environ.get('GOG_PATH')
    if os.environ.get('GMAIL_SERVICE_ACCOUNT_FILE'):
        cfg['gmailServiceAccountFile'] = os.environ['GMAIL_SERVICE_ACCOUNT_FILE']
    elif os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        cfg['gmailServiceAccountFile'] = os.environ['GOOGLE_APPLICATION_CREDENTIALS']

    return cfg


def get_gog_path(cfg: dict | None = None) -> str | None:
    cfg = cfg or load_config()
    path = cfg.get('gogPath') or shutil.which('gog')
    if path and Path(path).exists():
        return path
    if path:
        return path  # may be on PATH at runtime
    return shutil.which('gog')


def _run_cmd(cmd: list[str] | str, timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (result.stdout or '') + (result.stderr or '')
        return result.returncode == 0, out.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, ''


def discover_gog_accounts(gog_path: str | None = None) -> list[str]:
    """Try to list accounts configured in gog CLI."""
    gog = gog_path or get_gog_path()
    if not gog:
        return []

    for cmd in (
        [gog, 'auth', 'list', '-j'],
        [gog, 'auth', 'list'],
        [gog, 'accounts', 'list', '-j'],
    ):
        ok, out = _run_cmd(cmd)
        if not ok or not out:
            continue
        try:
            data = json.loads(out)
            if isinstance(data, list):
                emails = [a.get('email') or a.get('account') or str(a) for a in data if a]
                return [e for e in emails if '@' in str(e)]
            if isinstance(data, dict):
                accounts = data.get('accounts') or data.get('emails') or []
                return [a if '@' in str(a) else a.get('email', '') for a in accounts if a]
        except json.JSONDecodeError:
            emails = [line.strip() for line in out.splitlines() if '@' in line]
            if emails:
                return emails
    return []


def get_email_account(cfg: dict | None = None, required: bool = True) -> str | None:
    """Resolve the mailbox address from config, env, or gog discovery."""
    cfg = cfg or load_config()
    email = cfg.get('email') or os.environ.get('EMAIL_ACCOUNT')
    if email:
        return email.strip()

    accounts = discover_gog_accounts(get_gog_path(cfg))
    if len(accounts) == 1:
        return accounts[0]
    if len(accounts) > 1:
        raise ConfigError(
            'Multiple email accounts found in gog. Set EMAIL_SWIPE_EMAIL or add '
            f'"email" to {USER_CONFIG_FILE}. Found: {", ".join(accounts)}'
        )

    if required:
        raise ConfigError(
            'No email account configured.\n'
            f'  1. Create {USER_CONFIG_FILE} with {{"email": "you@example.com"}}\n'
            '  2. Or set environment variable: EMAIL_SWIPE_EMAIL=you@example.com\n'
            '  3. Or authenticate gog CLI: gog auth login'
        )
    return None


def discover_service_account_files() -> list[str]:
    """Search common locations for Gmail service account JSON."""
    candidates: list[str] = []

    env_path = os.environ.get('GMAIL_SERVICE_ACCOUNT_FILE') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if env_path:
        candidates.append(env_path)

    cfg = load_config()
    if cfg.get('gmailServiceAccountFile'):
        candidates.append(cfg['gmailServiceAccountFile'])

    home = Path.home()
    patterns = [
        home / '.config' / 'email-swipe' / 'service-account.json',
        home / '.config' / 'gog' / 'service-account.json',
        home / '.config' / 'gogcli' / 'service-account.json',
        home / '.local' / 'share' / 'gogcli' / 'sa-*.json',
    ]
    for pattern in patterns:
        if '*' in str(pattern):
            candidates.extend(glob.glob(str(pattern)))
        elif pattern.exists():
            candidates.append(str(pattern))

    seen = set()
    found = []
    for path in candidates:
        p = str(Path(path).expanduser())
        if p not in seen and Path(p).is_file():
            seen.add(p)
            found.append(p)
    return found


def get_service_account_file(cfg: dict | None = None, required: bool = True) -> str | None:
    files = discover_service_account_files()
    if files:
        return files[0]
    if required:
        raise ConfigError(
            'No Gmail service account file found.\n'
            '  Set GMAIL_SERVICE_ACCOUNT_FILE=/path/to/service-account.json\n'
            f'  Or save to {USER_CONFIG_DIR / "service-account.json"}'
        )
    return None


def config_status() -> dict:
    """Summary for preflight / detect-environment."""
    cfg = load_config()
    gog = get_gog_path(cfg)
    email = None
    email_error = None
    try:
        email = get_email_account(cfg, required=False)
    except ConfigError as e:
        email_error = str(e)

    sa_files = discover_service_account_files()

    return {
        'configFile': str(USER_CONFIG_FILE) if USER_CONFIG_FILE.exists() else None,
        'email': email,
        'emailConfigured': bool(email),
        'emailError': email_error,
        'gogAvailable': bool(gog),
        'gogPath': gog,
        'gogAccounts': discover_gog_accounts(gog) if gog else [],
        'serviceAccountFiles': sa_files,
        'imapConfigured': bool(os.environ.get('IMAP_SERVER') or cfg.get('imap')),
        'gmailMcpConfigured': bool(os.environ.get('GOOGLE_ACCESS_TOKEN') or os.environ.get('GMAIL_MCP_TOKEN')),
        'msgraphConfigured': bool(os.environ.get('MSGRAPH_TOKEN') or os.environ.get('OUTLOOK_TOKEN')),
    }


def ensure_user_config_dir():
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
