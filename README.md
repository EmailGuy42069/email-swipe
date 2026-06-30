# Email Swipe

Tinder-style email triage that teaches your AI agent what you want kept vs. spam.

**Local-first. No backend. The agent pulls your mail; you swipe in the browser.**

## How it works

```
Agent fetches inbox → injects emails.json → you swipe → export preferences.json → agent learns
```

| Swipe | Meaning |
|-------|---------|
| ← Left | Spam |
| → Right | Keep |

Toggle **Advanced** for folder routing (archive, important, unsubscribe, block).

## Quick start

```bash
# 1. Agent verifies mail access and fetches ~50 emails
python scripts/inject-emails.py my-inbox.json

# 2. Preflight + start
python scripts/preflight.py
python scripts/serve-ui.py
```

Open http://localhost:8765 (or the mobile URL printed in terminal).

**Demo mode:** leave `emails.json` empty — sample emails load automatically.

## After training

1. Tap **⬇️** in the UI to download `preferences.json`
2. Import for your agent:

```bash
python scripts/import-preferences.py ~/Downloads/preferences.json
```

Saved to `~/.config/email-swipe/preferences.json`

## Install

**OpenClaw:**
```bash
openclaw skills install github.com/<org>/email-swipe
openclaw skills run email-swipe
```

**Manual:**
```bash
git clone https://github.com/<org>/email-swipe.git
cd email-swipe
python scripts/serve-ui.py
```

## For agents

Read [SKILL.md](SKILL.md) for the full lifecycle:

1. Ask deployment preference (desktop / phone / OpenClaw)
2. Verify email access before training
3. Inject inbox → run session → remind user to export
4. Import preferences into agent context

See also:
- [references/deployment.md](references/deployment.md)
- [references/email-access.md](references/email-access.md)

## Project structure

```
email-swipe/
├── SKILL.md                 # Agent instructions
├── scripts/
│   ├── serve-ui.py          # Local server :8765
│   ├── inject-emails.py     # Agent → emails.json
│   ├── preflight.py         # Session checks
│   ├── import-preferences.py
│   └── watch-preferences.py # MCP server
├── assets/ui/               # Swipe interface
└── references/              # Deployment + email access guides
```

## License

MIT — see [LICENSE](LICENSE)
