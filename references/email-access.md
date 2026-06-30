# Email Access (Agent Responsibility)

The UI does **not** connect to email. The **agent** must pull messages using whatever mail tooling the user already has.

## Before the first session

Ask the user:

1. **Which email provider?** (Gmail, Outlook, Fastmail, iCloud, work Exchange, etc.)
2. **Is mail already connected to you?** (Gmail MCP, IMAP skill, OAuth connector, `gh` N/A, etc.)
3. **If not connected** — help them set up access first. Do not start Email Swipe until you can fetch inbox messages.

## Verify access

Run a small fetch (5–10 messages) and confirm you receive:

- `id` (stable message id)
- `from` / `sender`
- `subject`
- `snippet` or body text
- `html` (optional but recommended)

If fetch fails, stop and troubleshoot the mail connector — not this skill.

## Recommended fetch

| Goal | Guidance |
|------|----------|
| Training quality | 30–50 recent inbox emails, mixed senders |
| Diversity | Include newsletters, receipts, social, work — not only one sender |
| Privacy | User reviews in local UI; nothing uploaded by this skill |
| HTML bodies | Pass `html` when available so user can scroll before swiping |

## Provider notes

### Gmail (via agent MCP / API)
- Scope: read-only is enough (`gmail.readonly`); modify not required for training
- Fetch metadata + snippet + `format=full` or `format=raw` for HTML body
- Strip scripts; pass sanitized HTML in `html` field

### IMAP (generic)
- Use `UID` as `id`
- `BODY[TEXT]` or `BODY[HTML]` for content
- Parse `From`, `Subject`, `Date` headers

### Outlook / Microsoft Graph
- Use Graph message `id`
- `body.content` → `html` or `snippet`

## Inject into UI

```bash
python scripts/inject-emails.py references/email-batch.example.json
# or pipe JSON on stdin
```

Writes to `assets/ui/emails.json` (gitignored, local only).

## After training

Exported `preferences.json` contains **sender addresses and subject/snippet text** from swiped mail. Treat as sensitive user data; store only where the user expects (`~/.config/email-swipe/`).
