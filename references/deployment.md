# Deployment Options

The agent **must ask** how the user wants to use the UI before starting a session.

## Option A — Desktop browser (default)

```bash
python scripts/preflight.py   # checks inbox + prints URLs
python scripts/serve-ui.py
```

Open http://localhost:8765

**Best for:** quick sessions, mouse + keyboard, dev testing.

## Option B — Phone on same Wi‑Fi

```bash
python scripts/serve-ui.py
```

Server prints a **Mobile** URL, e.g. `http://192.168.1.2:8765`

**Requirements:**
- Phone and computer on the same network
- Mac firewall allows incoming connections for Python (if blocked)

**Best for:** natural swipe gestures, training on the couch.

## Option C — OpenClaw skill install

```bash
openclaw skills install github.com/<org>/email-swipe
openclaw skills run email-swipe
```

Skill root: `~/.openclaw/skills/email-swipe/`

**Best for:** users already on OpenClaw.

## Option D — Manual clone

```bash
git clone https://github.com/<org>/email-swipe.git
cd email-swipe
python scripts/serve-ui.py
```

**Best for:** contributors, Cursor users, custom forks.

## Option E — Demo only (no real mail)

If the user wants to **try the UI** before connecting email:

- Leave `emails.json` empty — UI loads `demo-emails.json` automatically
- Remind them this does **not** train on their real preferences

## Agent checklist (ask in conversation)

```
□ How do you want to deploy? (desktop / phone / OpenClaw)
□ Is your email accessible to me right now?
□ Ready to pull ~50 inbox emails for a training session?
□ After swiping, I'll remind you to export and send me preferences.json
```
