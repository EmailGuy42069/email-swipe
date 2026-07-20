#!/usr/bin/env python3
"""
Fetch emails using whatever provider is available.
Auto-detects: gog, gmail-mcp, imap, msgraph
"""

import json
import subprocess
import sys
import os
import argparse

from email_config import ConfigError, get_email_account, get_gog_path, load_config


def run_cmd(cmd, timeout=30):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout
        print(f"Command failed: {result.stderr}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return None


def fetch_with_gog(limit=50):
    """Fetch emails using gog CLI."""
    cfg = load_config()
    gog_path = get_gog_path(cfg)
    if not gog_path:
        print("gog CLI not found. Install gog or set EMAIL_SWIPE_GOG_PATH.", file=sys.stderr)
        return None

    try:
        account = get_email_account(cfg)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return None

    cmd = f"{gog_path} gmail messages search in:inbox -a {account} --max {limit} -j --results-only"
    output = run_cmd(cmd)
    if not output:
        return None

    try:
        messages = json.loads(output)
        if not isinstance(messages, list):
            messages = messages.get("messages", [])
    except Exception as e:
        print(f"Failed to parse gog output: {e}", file=sys.stderr)
        return None

    emails = []
    for msg in messages[:limit]:
        from_field = msg.get("from", "")

        sender = from_field
        if "<" in from_field:
            sender = from_field.split("<")[0].strip()
        elif "@" in from_field:
            sender = from_field.split("@")[0]

        sender = sender.replace('"', '').strip()

        email = {
            "id": msg.get("id", ""),
            "sender": sender or "Unknown",
            "from": from_field,
            "subject": msg.get("subject", "(no subject)"),
            "snippet": "",
            "date": msg.get("date", ""),
            "labels": msg.get("labels", []),
            "threadId": msg.get("threadId", "")
        }
        emails.append(email)

    return emails


def fetch_with_imap(limit=50):
    """Fetch emails using IMAP."""
    print("IMAP fetch not yet implemented", file=sys.stderr)
    return None


def fetch_emails(provider=None, limit=50):
    """Fetch emails using the best available provider."""
    providers = {
        "gog": fetch_with_gog,
        "imap": fetch_with_imap,
    }

    if provider:
        if provider in providers:
            return providers[provider](limit)
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return None

    for name, fetch_func in providers.items():
        print(f"Trying {name}...", file=sys.stderr)
        result = fetch_func(limit)
        if result:
            print(f"Successfully fetched {len(result)} emails via {name}", file=sys.stderr)
            return result

    print("No email provider available", file=sys.stderr)
    return None


def main():
    parser = argparse.ArgumentParser(description="Fetch emails for swipe training")
    parser.add_argument("--provider", help="Force specific provider (gog, imap)")
    parser.add_argument("--limit", type=int, default=50, help="Number of emails to fetch")
    parser.add_argument("--output", "-o", default="emails.json", help="Output file")
    parser.add_argument("--account", "-a", help="Email account (overrides config)")
    args = parser.parse_args()

    if args.account:
        os.environ["EMAIL_SWIPE_EMAIL"] = args.account

    emails = fetch_emails(args.provider, args.limit)

    if emails:
        with open(args.output, "w") as f:
            json.dump(emails, f, indent=2)
        print(f"Saved {len(emails)} emails to {args.output}")
        return 0
    print("Failed to fetch emails")
    return 1


if __name__ == "__main__":
    sys.exit(main())
