#!/usr/bin/env python3
"""
Fetch emails with full HTML content using Gmail API directly.
Uses service account credentials from config or standard env paths.
"""

import json
import os
import sys
import base64
import argparse

from email_config import ConfigError, get_email_account, get_service_account_file

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_gmail_service():
    """Get Gmail service using configured service account credentials."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
    except ImportError:
        print(
            "google-api-python-client and google-auth are required.\n"
            "  pip install google-api-python-client google-auth",
            file=sys.stderr,
        )
        return None

    try:
        sa_path = get_service_account_file()
        account = get_email_account()
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return None

    credentials = service_account.Credentials.from_service_account_file(
        sa_path, scopes=SCOPES, subject=account)

    return build('gmail', 'v1', credentials=credentials)


def get_message_body(payload):
    """Extract HTML and text body from message payload."""
    html = ""
    text = ""

    def decode_part(data):
        if not data:
            return ""
        padded = data + '=' * (4 - len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode('utf-8', errors='ignore')

    def extract_parts(parts):
        nonlocal html, text
        for part in parts:
            mime_type = part.get('mimeType', '')
            body = part.get('body', {})

            if mime_type == 'text/html' and 'data' in body:
                html = decode_part(body['data'])
            elif mime_type == 'text/plain' and 'data' in body:
                text = decode_part(body['data'])
            elif 'parts' in part:
                extract_parts(part['parts'])

    if 'parts' in payload:
        extract_parts(payload['parts'])
    elif 'body' in payload:
        mime_type = payload.get('mimeType', '')
        data = payload['body'].get('data', '')
        if mime_type == 'text/html':
            html = decode_part(data)
        elif mime_type == 'text/plain':
            text = decode_part(data)

    return html, text


def fetch_emails(limit=50):
    """Fetch emails with full content."""
    service = get_gmail_service()
    if not service:
        return None

    try:
        results = service.users().messages().list(
            userId='me',
            labelIds=['INBOX'],
            maxResults=limit
        ).execute()

        messages = results.get('messages', [])
        emails = []

        for msg_meta in messages:
            msg_id = msg_meta['id']

            msg = service.users().messages().get(
                userId='me',
                id=msg_id,
                format='full'
            ).execute()

            headers = {h['name'].lower(): h['value']
                      for h in msg['payload'].get('headers', [])}

            html, text = get_message_body(msg['payload'])
            snippet = msg.get('snippet', '')

            from_field = headers.get('from', '')
            sender = from_field
            if '<' in from_field:
                sender = from_field.split('<')[0].strip().replace('"', '')
            elif '@' in from_field:
                sender = from_field.split('@')[0]

            has_attachment = any(
                part.get('filename')
                for part in msg['payload'].get('parts', [])
                if part.get('filename')
            )

            is_newsletter = 'list-unsubscribe' in headers or \
                          'mailing list' in headers.get('precedence', '').lower()

            email = {
                "id": msg_id,
                "sender": sender or "Unknown",
                "from": from_field,
                "subject": headers.get('subject', '(no subject)'),
                "snippet": snippet[:300] if snippet else text[:300] if text else "",
                "html": html if html else f"<pre>{text}</pre>" if text else "",
                "date": headers.get('date', ''),
                "labels": msg.get('labelIds', []),
                "threadId": msg.get('threadId', ''),
                "hasAttachment": has_attachment,
                "isNewsletter": is_newsletter
            }
            emails.append(email)

        return emails

    except Exception as e:
        print(f"Error fetching emails: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch emails with HTML content")
    parser.add_argument("--limit", type=int, default=50, help="Number of emails")
    parser.add_argument("--output", "-o", default="emails.json", help="Output file")
    parser.add_argument("--account", "-a", help="Email account (overrides config)")
    args = parser.parse_args()

    if args.account:
        os.environ["EMAIL_SWIPE_EMAIL"] = args.account

    emails = fetch_emails(args.limit)

    if emails:
        with open(args.output, 'w') as f:
            json.dump(emails, f, indent=2)
        print(f"Saved {len(emails)} emails to {args.output}")

        ui_path = os.path.join(os.path.dirname(__file__), '../assets/ui/emails.json')
        with open(ui_path, 'w') as f:
            json.dump(emails, f, indent=2)
        print(f"Also saved to {ui_path}")
        return 0
    print("Failed to fetch emails")
    return 1


if __name__ == "__main__":
    sys.exit(main())
