#!/usr/bin/env python3
"""Interactive setup for email-swipe configuration."""

import json
import sys
from pathlib import Path

from email_config import (
    USER_CONFIG_DIR,
    USER_CONFIG_FILE,
    discover_gog_accounts,
    discover_service_account_files,
    ensure_user_config_dir,
    get_gog_path,
)


def prompt(label, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def main():
    print("=== Email Swipe — Configuration Setup ===\n")
    print(f"Config will be saved to: {USER_CONFIG_FILE}\n")

    ensure_user_config_dir()

    existing = {}
    if USER_CONFIG_FILE.exists():
        with open(USER_CONFIG_FILE) as f:
            existing = json.load(f)
        print(f"Existing config found. Press Enter to keep current values.\n")

    gog_path = get_gog_path(existing)
    gog_accounts = discover_gog_accounts(gog_path) if gog_path else []
    sa_files = discover_service_account_files()

    default_email = existing.get("email") or (gog_accounts[0] if len(gog_accounts) == 1 else None)
    email = prompt("Email address", default_email)
    if not email:
        print("Email is required.", file=sys.stderr)
        return 1

    default_gog = existing.get("gogPath") or gog_path
    gog_path_input = prompt("gog CLI path (leave blank for PATH lookup)", default_gog)

    default_sa = existing.get("gmailServiceAccountFile") or (sa_files[0] if sa_files else None)
    sa_input = prompt("Gmail service account JSON (optional)", default_sa)

    config = {
        "email": email,
    }
    if gog_path_input:
        config["gogPath"] = gog_path_input
    if sa_input:
        config["gmailServiceAccountFile"] = sa_input

    with open(USER_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"\n✓ Saved {USER_CONFIG_FILE}")
    print("\nYou can also set environment variables:")
    print("  EMAIL_SWIPE_EMAIL=you@example.com")
    print("  GMAIL_SERVICE_ACCOUNT_FILE=/path/to/service-account.json")
    print("  EMAIL_SWIPE_GOG_PATH=/path/to/gog")
    print("\nRun: python scripts/detect-environment.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
