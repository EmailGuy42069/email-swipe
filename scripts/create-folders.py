#!/usr/bin/env python3
"""Create folders in Gmail from folder-requests.json."""

import json
import sys
import os
import subprocess

from email_config import ConfigError, get_email_account, get_gog_path, get_service_account_file, load_config


def create_label_gog(name):
    """Create a label in Gmail using gog CLI."""
    cfg = load_config()
    gog_path = get_gog_path(cfg)
    if not gog_path:
        return False, "gog CLI not found"

    try:
        account = get_email_account(cfg)
    except ConfigError as e:
        return False, str(e)

    cmd = [gog_path, "gmail", "labels", "create", name, "-a", account]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr if result.returncode != 0 else "Created"


def create_label_api(name):
    """Create a label using Gmail API directly."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
    except ImportError:
        return False, "google-api-python-client not installed"

    scopes = ['https://www.googleapis.com/auth/gmail.modify']

    try:
        sa_path = get_service_account_file()
        account = get_email_account()
    except ConfigError as e:
        return False, str(e)

    try:
        credentials = service_account.Credentials.from_service_account_file(
            sa_path, scopes=scopes, subject=account)
        service = build('gmail', 'v1', credentials=credentials)

        label_object = {
            'name': name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show'
        }

        result = service.users().labels().create(userId='me', body=label_object).execute()
        return True, result.get('id')
    except Exception as e:
        return False, str(e)


def main():
    if len(sys.argv) < 2:
        print("Usage: create-folders.py <folder-requests.json>", file=sys.stderr)
        return 1

    requests_file = sys.argv[1]

    if not os.path.exists(requests_file):
        print(f"File not found: {requests_file}", file=sys.stderr)
        return 1

    with open(requests_file) as f:
        data = json.load(f)

    folders = data.get("createFolders", [])

    if not folders:
        print("No folders to create", file=sys.stderr)
        return 0

    print(f"Creating {len(folders)} folder(s)...", file=sys.stderr)

    created = []
    failed = []

    for folder in folders:
        name = folder.get("name")
        if not name:
            continue

        print(f"  Creating '{name}'...", file=sys.stderr)

        success, result = create_label_api(name)
        if not success:
            success, result = create_label_gog(name)

        if success:
            created.append({"name": name, "id": result})
            print("    ✓ Created", file=sys.stderr)
        else:
            failed.append({"name": name, "error": result})
            print(f"    ✗ Failed: {result}", file=sys.stderr)

    output = {
        "created": created,
        "failed": failed,
        "total": len(folders),
        "success": len(created)
    }

    print(json.dumps(output, indent=2))

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
