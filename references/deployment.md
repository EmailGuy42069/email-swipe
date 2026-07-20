# Deployment Options

Email Swipe is **local-first**. The supported default is: run `serve-ui.py` on the user's machine, open the URL it prints, and let artifacts persist under `~/.config/email-swipe/`.

No cloud host, PaaS, or specific agent product is required. Users bring their own stack.

## What you need (minimum)

| Piece | Required? | Examples (pick what you have) |
|-------|-----------|----------------------------------|
| Python 3 | Yes | System Python, pyenv, conda |
| Browser | Yes (for swipe UI paths) | Desktop or mobile |
| Agent host | Yes (for full skill) | Cursor, OpenClaw, Claude Code, any MCP client |
| Mail access | For real training | Gmail MCP, `gog`, IMAP, Microsoft Graph, agent-native tools |
| Cloud / Render / VPS | **No** | Only if you choose remote UI access yourself |

Preflight: `python scripts/check-ready.py` (or MCP `get_skill_context`).

## Where data lives

When `serve-ui.py` runs **on the machine that owns the session**:

```
~/.config/email-swipe/
├── preferences.json      # Swipe data (sensitive)
├── settings.json         # Folder routes, agent name, etc.
├── assistant-brief.md    # Human-readable summary
├── policy-graph.json   # Structured rules
├── platform-rules.json # Label/folder suggestions
├── training-pack.json    # Slim agent runtime slice
├── runtime.json          # Active session URL + port (dynamic)
├── session-complete.json # Last finished session
└── session-history.json  # Score trend over sessions
```

The UI also uses browser storage (`IndexedDB`, `sessionStorage`) as **session cache** — authoritative training output is on disk under `~/.config/email-swipe/` after compile.

**Read the Desktop URL from server output or `runtime.json`** — do not hardcode a port (e.g. 8765).

## Option A — Desktop browser (default)

```bash
python scripts/check-ready.py   # optional
python scripts/serve-ui.py
```

Open the **Desktop URL** printed at startup.

**Best for:** most users, quick sessions, mouse + keyboard.

## Option B — Phone on same Wi‑Fi

```bash
python scripts/serve-ui.py
```

Server prints a **Mobile** URL (LAN IP + dynamic port), e.g. `http://192.168.1.2:54321`

**Requirements:**
- Phone and computer on the same network
- Firewall allows incoming connections for Python (if blocked)

**Best for:** swipe gestures on a phone while the server runs on your laptop.

Data still persists on the **computer** running `serve-ui.py`.

## Option C — Agent skill install (any MCP host)

Install or clone the repo, then register MCP in your agent's config (Cursor, OpenClaw, etc.):

```json
{
  "mcpServers": {
    "email-swipe": {
      "command": "python3",
      "args": ["/path/to/email-swipe/scripts/watch-preferences.py"]
    }
  }
}
```

OpenClaw example:

```bash
openclaw skills install github.com/EmailGuy42069/email-swipe
openclaw skills run email-swipe
```

**Best for:** users who already run an agent with MCP — the skill does not mandate a specific product.

## Option D — Manual clone

```bash
git clone https://github.com/EmailGuy42069/email-swipe.git
cd email-swipe
python scripts/serve-ui.py
```

**Best for:** contributors, Cursor users, custom forks.

## Option E — Demo only (no real mail)

If the user wants to **try the UI** before connecting email:

- Leave `emails.json` empty — UI loads `demo-emails.json` automatically
- Or: `python scripts/session-intake.py demo`
- Remind them this does **not** train on their real preferences

## Option F — Remote UI access (user-provided)

Some users expose the **local** UI through a tunnel or VPN so they can swipe from another device or share a link with their agent:

- SSH port forward
- Tailscale / ZeroTier
- ngrok, Cloudflare Tunnel, etc.

**Persistence:** Same as local — data stays on the machine running `serve-ui.py`, as long as that process is what the tunnel points at.

**Power users:** Enable *Explore remote access* in Settings → Access, or read [remote-access-power-user.md](./remote-access-power-user.md) for Tailscale, VPS, tunnel, and security patterns (always-on URL like Telegram, without Email Swipe hosting mail).

The agent **must ask** how the user wants to reach the UI before starting a session.

## Option G — Hosted UI on ephemeral infrastructure (advanced)

Running `serve-ui.py` on a **remote server with ephemeral disk** (containers, some PaaS deploys, serverless) means `~/.config/email-swipe/` may **reset on restart or redeploy**.

If you host this way, you must configure **durable storage** yourself (mounted volume, S3-compatible store, database, etc.). Email Swipe does not ship a one-size-fits-all cloud persistence layer.

The repo root includes an optional `render.yaml` Blueprint — **maintainer example only**, not a customer requirement. Future work may add `EMAIL_SWIPE_DATA_DIR` for operators who host remotely; see `docs/IMPLEMENTATION-CHECKLIST.md` (P0-1).

## import-sorting (no UI)

Users with organized folders can skip the swipe UI entirely. The agent runs backend-only learning — see [paths/import-sorting.md](./paths/import-sorting.md). Still requires verified mail/folder access via whatever provider tools the user has.

## Agent checklist (ask in conversation)

```
□ Where will serve-ui.py run? (your laptop = default; remote only if you understand persistence)
□ How will you open the UI? (desktop / phone on Wi‑Fi / tunnel — use printed URL or runtime.json)
□ Which agent host? (Cursor, OpenClaw, other MCP — no specific product required)
□ Do I have access to your email? (MCP, gog, IMAP, Graph, or other — see email-access-gate.md)
□ Real inbox or demo first?
□ Ready to pull ~50 inbox emails with full body/HTML when available (or use demo)?
□ After training, I'll present assistant-brief.md — no manual export if serve-ui compiled successfully
```
