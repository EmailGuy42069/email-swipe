#!/usr/bin/env python3
"""
Detect available email access methods and recommend the best one.
Returns JSON with available providers and recommended approach.
"""

import json
import subprocess
import shutil
import os
import sys

from email_config import (
    ConfigError,
    config_status,
    get_email_account,
    get_gog_path,
    load_config,
)


def run_cmd(cmd, capture=True):
    """Run a command and return output or None if fails."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=capture,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() if capture else True
        return None
    except Exception:
        return None


def check_gog():
    """Check if gog CLI is available and authenticated."""
    cfg = load_config()
    gog_path = get_gog_path(cfg)
    if not gog_path:
        return None

    try:
        account = get_email_account(cfg)
    except ConfigError:
        return {
            "name": "gog",
            "path": gog_path,
            "type": "cli",
            "note": "gog found but no email account configured",
            "priority": 1,
            "configured": False,
        }

    result = run_cmd(f"{gog_path} gmail labels list -a {account} 2>&1")
    if result and "error" not in result.lower() and "unauthorized" not in result.lower():
        return {
            "name": "gog",
            "path": gog_path,
            "account": account,
            "type": "cli",
            "fetch_cmd": f"{gog_path} gmail messages search in:inbox -a {account} --max 50 -j",
            "priority": 1,
            "configured": True,
        }
    return None


def check_gmail_mcp():
    """Check if gmail-mcp is available."""
    if os.environ.get("GOOGLE_ACCESS_TOKEN") or os.environ.get("GMAIL_MCP_TOKEN"):
        return {
            "name": "gmail-mcp",
            "type": "mcp",
            "priority": 2,
            "configured": True,
        }
    return None


def check_gmail_api():
    """Check if Gmail API service account credentials are available."""
    from email_config import discover_service_account_files, get_email_account

    sa_files = discover_service_account_files()
    if not sa_files:
        return None

    try:
        account = get_email_account(required=False)
    except ConfigError:
        account = None

    return {
        "name": "gmail-api",
        "type": "api",
        "serviceAccountFile": sa_files[0],
        "account": account,
        "note": "Uses service account + domain-wide delegation" if account else "Set email in config for delegation",
        "priority": 1,
        "configured": bool(account),
    }


def check_imap():
    """Check if IMAP credentials are configured."""
    cfg = load_config()
    imap_env = os.environ.get("IMAP_SERVER") or os.environ.get("EMAIL_IMAP") or cfg.get("imap")
    if imap_env:
        return {
            "name": "imap",
            "type": "protocol",
            "priority": 3
        }
    return None


def check_msgraph():
    """Check if Microsoft Graph is available."""
    if os.environ.get("MSGRAPH_TOKEN") or os.environ.get("OUTLOOK_TOKEN"):
        return {
            "name": "msgraph",
            "type": "api",
            "priority": 2
        }
    return None


def detect_environment():
    """Detect the runtime environment."""
    env = {
        "is_vps": False,
        "has_tailscale": False,
        "cloudflare_available": shutil.which("cloudflared") is not None,
        "ssh_available": True,
        "local_access": False
    }

    if not os.environ.get("DISPLAY") and not shutil.which("gnome-shell"):
        env["is_vps"] = True

    if shutil.which("tailscale"):
        result = run_cmd("tailscale status 2>&1 | head -1")
        if result and "error" not in result.lower():
            env["has_tailscale"] = True

    if os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        env["local_access"] = False
    elif not env["is_vps"]:
        env["local_access"] = True

    return env


def recommend_deployment(env):
    """Recommend deployment method based on environment."""
    from session_state import load_runtime

    runtime = load_runtime()
    if runtime.get('desktopUrl'):
        return {
            'method': 'localhost',
            'url': runtime['desktopUrl'],
            'note': 'From runtime.json — server already running or last session',
        }

    port_hint = os.environ.get('PORT', '<dynamic>')
    localhost = f'http://localhost:{port_hint}'

    if env['local_access']:
        return {
            'method': 'localhost',
            'url': localhost,
            'note': 'User is on same machine as agent — run serve-ui.py for Desktop URL',
        }

    if env['has_tailscale']:
        return {
            "method": "tailscale",
            "note": "Use tailscale IP for secure access",
            "requires": "tailscale status to get IP"
        }

    if env["cloudflare_available"]:
        return {
            "method": "cloudflare_tunnel",
            'cmd': f'cloudflared tunnel --url http://localhost:{port_hint}',
            "note": "Creates temporary public URL (good for phones)"
        }

    if env["is_vps"]:
        return {
            "method": "vps_public_ip",
            "note": "VPS has public IP but may need firewall rules",
            'warning': f'Port {port_hint} must be open in firewall (or use serve-ui dynamic port)',
        }

    return {
        "method": "ssh_tunnel",
        'cmd': f'ssh -L {port_hint}:localhost:{port_hint} <host>',
        "note": "Requires SSH access from user's machine"
    }


def main():
    providers = []

    for checker in [check_gog, check_gmail_api, check_gmail_mcp, check_imap, check_msgraph]:
        result = checker()
        if result:
            providers.append(result)

    providers.sort(key=lambda x: x.get("priority", 99))

    env = detect_environment()
    deployment = recommend_deployment(env)
    status = config_status()

    configured_providers = [p for p in providers if p.get("configured", True)]
    output = {
        "email_providers": providers,
        "recommended_provider": configured_providers[0]["name"] if configured_providers else None,
        "configuration": status,
        "environment": env,
        "recommended_deployment": deployment,
        "ready_for_training": len(configured_providers) > 0,
    }

    print(json.dumps(output, indent=2))
    return 0 if configured_providers else 1


if __name__ == "__main__":
    sys.exit(main())
