---
name: email-swipe
description: Tinder-style email triage UI that generates training data for AI agents to learn your email preferences. Use when the user wants to (1) quickly sort through a cluttered inbox with swipe gestures, (2) train their AI agent (Claude Code, OpenClaw) how to handle emails automatically, (3) generate few-shot examples for LLM email classification, or (4) build a personalized email preference file for agent consumption. Creates local-first training data that teaches agents what to show, hide, prioritize, or flag based on user behavior.
---

# Email Swipe Skill

Tinder-style **spam / keep** training UI. The agent owns email access; the UI only displays what the agent injects. All data stays local.

## When to use this skill

- User wants to train an agent on email triage preferences
- User has (or can set up) email access through the agent
- User is willing to swipe ~30–50 emails in a local browser session

## Full lifecycle (agent must follow)

### Phase 1 — Install

Pick one path with the user:

| Method | Command |
|--------|---------|
| OpenClaw | `openclaw skills install github.com/<org>/email-swipe` |
| Git clone | `git clone https://github.com/<org>/email-swipe.git` |
| Already in workspace | use `./scripts/` from skill root |

Requirements: **Python 3** only. No npm, no backend.

### Phase 2 — Ask deployment preference (required)

**Do not skip.** Ask: *"How do you want to run Email Swipe?"*

See [references/deployment.md](references/deployment.md):

- **Desktop** — `http://localhost:8765`
- **Phone (same Wi‑Fi)** — LAN URL printed by `serve-ui.py`
- **Demo first** — empty `emails.json` loads sample emails (not real training)
- **OpenClaw** — `openclaw skills run email-swipe`

Run preflight and share URLs:

```bash
python scripts/preflight.py
python scripts/serve-ui.py
```

### Phase 3 — Verify email access (required before real training)

**Do not start a real training session until the agent can pull mail.**

Ask: *"Is your email connected so I can read your inbox?"*

If **no** → help set up Gmail MCP, IMAP, Graph API, or whatever connector the environment supports. See [references/email-access.md](references/email-access.md).

If **yes** → fetch a test batch (5 messages) to confirm fields, then fetch **30–50 inbox emails**.

### Phase 4 — Inject inbox

```bash
python scripts/inject-emails.py /path/to/batch.json
```

Email schema — include `html` when available:

```json
{
  "id": "msg-123",
  "sender": "GitHub",
  "from": "notifications@github.com",
  "subject": "New PR opened",
  "snippet": "Plain preview for training export",
  "html": "<p>Full body (optional, sandboxed in UI)</p>",
  "date": "2h ago",
  "hasAttachment": false,
  "isNewsletter": false
}
```

Example file: [references/email-batch.example.json](references/email-batch.example.json)

### Phase 5 — Training session

1. Start server: `python scripts/serve-ui.py`
2. User opens URL (desktop or phone)
3. First card: **← Spam    Keep →** (instructions)
4. User swipes left = spam, right = keep
5. **Advanced toggle** — optional folder routing (archive, important, unsubscribe, block)
6. Aim for **30–50 swipes** for useful training data

**During session:** do not close the server. Preferences accumulate in browser IndexedDB.

### Phase 6 — Export & import (required reminder)

When the user finishes (or inbox is empty), **remind them explicitly:**

> *"Tap the ⬇️ button to download `preferences.json`. Then share that file with me (or tell me where it saved) so I can import your email preferences."*

The browser downloads to the user's Downloads folder. Import into the standard path:

```bash
python scripts/import-preferences.py ~/Downloads/preferences.json
```

Stored at: `~/.config/email-swipe/preferences.json`

**Agent:** read this file and use `fewShotExamples`, `senderRules`, and `patterns` for future email triage.

### Phase 7 — Ongoing use

- **Retrain** — pull a fresh batch, new session, merge or replace preferences
- **Live updates** — optional MCP: `python scripts/watch-preferences.py`
- **Export from browser API** — `EmailSwipe.exportPreferences()` in devtools

## Agent conversation script

Use this flow in natural language:

1. "Want to train me on your email preferences? I'll need access to your inbox."
2. "How do you want to run the swipe UI — on this computer, or on your phone over Wi‑Fi?"
3. *[verify mail access → fetch → inject]*
4. "I've loaded N emails. Open [URL] and swipe left for spam, right for keep."
5. *[after session]* "Please export your preferences (⬇️ button) and send me the file."
6. *[import]* "Got it — I'll use these rules when triaging your mail."

## Architecture

| Piece | Role |
|-------|------|
| `assets/ui/` | Static swipe UI (browser only) |
| `emails.json` | Agent-written inbox queue (gitignored) |
| IndexedDB | In-browser swipe storage |
| `preferences.json` | Exported training data for agents |
| `scripts/` | inject, serve, import, export, preflight, MCP watch |

## Scripts

| Script | Purpose |
|--------|---------|
| `preflight.py` | Check inbox + print deployment URLs |
| `inject-emails.py` | Write agent-fetched mail → `emails.json` |
| `serve-ui.py` | Start local server (port 8765) |
| `import-preferences.py` | Copy exported JSON → `~/.config/email-swipe/` |
| `export-preferences.py` | Process raw swipe export (CLI) |
| `watch-preferences.py` | MCP server for live preference reads |

## Resources

- [references/deployment.md](references/deployment.md) — desktop, mobile, OpenClaw
- [references/email-access.md](references/email-access.md) — agent mail fetch guide
- [references/email-batch.example.json](references/email-batch.example.json) — inject format

## Privacy

- UI never calls email APIs
- OAuth/tokens stay in the **agent's** mail connector, not this skill
- `preferences.json` contains sender/subject snippets — handle as sensitive
- No telemetry, no cloud backend
