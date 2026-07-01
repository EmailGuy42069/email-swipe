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
    gog_path = "/root/go/bin/gog"
    if not os.path.exists(gog_path):
        gog_path = "gog"  # Try PATH
    
    account = "blake@blakemcginn.com"
    
    # Search for recent messages in inbox
    # gog uses: gmail messages search <query> --max N
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
        # gog search returns: id, from, subject, date, labels, threadId
        from_field = msg.get("from", "")
        
        # Extract sender name
        sender = from_field
        if "<" in from_field:
            sender = from_field.split("<")[0].strip()
        elif "@" in from_field:
            sender = from_field.split("@")[0]
        
        # Clean up sender
        sender = sender.replace('"', '').strip()
        
        email = {
            "id": msg.get("id", ""),
            "sender": sender or "Unknown",
            "from": from_field,
            "subject": msg.get("subject", "(no subject)"),
            "snippet": "",  # gog search doesn't include snippet, would need separate call
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
    """
    Fetch emails using the best available provider.
    If provider is specified, use that. Otherwise auto-detect.
    """
    providers = {
        "gog": fetch_with_gog,
        "imap": fetch_with_imap,
        # Add more providers here
    }
    
    if provider:
        if provider in providers:
            return providers[provider](limit)
        else:
            print(f"Unknown provider: {provider}", file=sys.stderr)
            return None
    
    # Auto-detect
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
    args = parser.parse_args()
    
    emails = fetch_emails(args.provider, args.limit)
    
    if emails:
        with open(args.output, "w") as f:
            json.dump(emails, f, indent=2)
        print(f"Saved {len(emails)} emails to {args.output}")
        return 0
    else:
        print("Failed to fetch emails")
        return 1

if __name__ == "__main__":
    sys.exit(main())
