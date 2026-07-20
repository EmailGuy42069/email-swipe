# Email Access (Agent Responsibility)

The UI does **not** connect to email. The **agent** must pull messages using whatever mail tooling the user already has.

## Configuration

Before using fetch scripts, configure the user's mailbox (nothing is hardcoded in the repo):

```bash
python scripts/setup-config.py
```

Or set environment variables:

```bash
export EMAIL_SWIPE_EMAIL=you@example.com
export GMAIL_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
```

Config file: `~/.config/email-swipe/config.json` — see [config.example.json](config.example.json).

Verify setup:

```bash
python scripts/detect-environment.py
python scripts/preflight.py
```

## Before the first session

**Run the email access gate:** [email-access-gate.md](email-access-gate.md)

Ask the user:

1. **Do I already have access to your email?** (Gmail MCP, gog, IMAP, Graph — local detect may miss MCP-only access)
2. **Which email provider?** (Gmail, Outlook, Fastmail, iCloud, work Exchange, etc.)
3. **Real inbox or demo first?**
4. **If not connected** — help them set up access or use demo/manual batch. Do not start real-mail training until fetch is verified.

Auto-detect: `python scripts/detect-environment.py` or MCP `check_email_access`

## Verify access

Run a small fetch (5–10 messages) and confirm you receive:

- `id` (stable message id)
- `from` / `sender`
- `subject`
- `snippet` or body text
- `html` (preferred default — fetch and read the full sanitized HTML/body whenever available)

If fetch returns only subject lines, treat that as **insufficient for quality training** unless the provider truly cannot supply bodies. Fix the mail fetch first.
If fetch fails, stop and troubleshoot the mail connector — not this skill.

## Recommended fetch

| Goal | Guidance |
|------|----------|
| Training quality | 30–50 recent inbox emails, mixed senders |
| Diversity | Include newsletters, receipts, social, work — not only one sender |
| Privacy | User reviews in local UI; nothing uploaded by this skill |
| HTML bodies | Pass full sanitized `html` whenever available so the user and agent are training on the actual message, not just the subject line |

## Provider notes

### Gmail (via agent MCP / API)
- Scope: read-only is enough (`gmail.readonly`); modify not required for training
- Fetch metadata + snippet + `format=full` or `format=raw` for the full message body
- Strip scripts; pass sanitized HTML in `html` field

### IMAP (generic)
- Use `UID` as `id`
- `BODY[TEXT]` or `BODY[HTML]` for full content, not just headers/subject
- Parse `From`, `Subject`, `Date` headers

### Outlook / Microsoft Graph
- Use Graph message `id`
- `body.content` → `html`; use `snippet` only as a fallback

## Inject into UI

```bash
python scripts/inject-emails.py references/email-batch.example.json
# or pipe JSON on stdin
```

Writes to `assets/ui/emails.json` (gitignored, local only).

## After training

Exported `preferences.json` contains **sender addresses and subject/snippet text** from swiped mail. Treat as sensitive user data; store only where the user expects (`~/.config/email-swipe/`).
