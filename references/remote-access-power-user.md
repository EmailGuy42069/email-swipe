# Remote access — power user guide

**Audience:** Technical users who want the Email Swipe UI and settings reachable from anywhere — similar to reaching an agent via Telegram — without Email Swipe hosting your mail.

**Not required** for most users. Default: run `serve-ui.py` on your machine, use Desktop or LAN URL.

---

## What you are solving

| Goal | What needs to be always reachable |
|------|-----------------------------------|
| Swipe training from phone/laptop anywhere | `serve-ui.py` (HTTP) |
| Settings + compiled rules | `~/.config/email-swipe/` on the **same host** as the UI |
| Agent help via Telegram | Your agent process (separate from Email Swipe) |

**Golden rule:** UI server and `~/.config/email-swipe/` should live on the **same always-on machine** as your agent + MCP, or you accept sync complexity.

---

## Option comparison

| Option | Always on? | HTTPS | Best for | Persistence |
|--------|------------|-------|----------|-------------|
| **A. Tailscale / ZeroTier** | If host is on | Yes (Tailscale Serve) | Private access, home server | On host disk |
| **B. VPS + volume** | Yes | You configure (Caddy) | Public URL, technical users | Mounted volume |
| **C. Cloudflare Tunnel** | If host is on | Yes | Expose home server safely | On host disk |
| **D. ngrok / quick tunnel** | While process runs | Yes | Demos, testing | On host disk |
| **E. SSH port forward** | While SSH up | Optional | Ad hoc from laptop | On laptop |
| **F. PaaS (Render, Fly)** | Yes | Yes | Demo only unless disk added | **Risky** without volume |
| **G. Agent-only (no remote UI)** | Agent via Telegram | N/A | Digests, no swiping | Local agent host |

---

## Recommended architecture (Telegram-parity)

Run **one always-on box** (Mac mini, NUC, small VPS):

```
┌─────────────────────────────────────────┐
│  Always-on host                          │
│  • OpenClaw / agent + Telegram bot       │
│  • watch-preferences.py (MCP)            │
│  • serve-ui.py (systemd / launchd)       │
│  • ~/.config/email-swipe/                │
└─────────────────────────────────────────┘
         ▲                    ▲
         │                    │
    Telegram              Browser / PWA
    (anywhere)            (Tailscale or HTTPS URL)
```

1. Agent and UI share one data directory.
2. Telegram talks to agent; agent sends stable UI link from `runtime.json`.
3. Phone: Add to Home Screen → your stable URL (see [ADVANCED-SETTINGS-SPEC](../docs/ADVANCED-SETTINGS-SPEC.md) § Mobile).

---

## Option A — Tailscale (recommended for home server)

**Why:** Private network, stable hostname, no public exposure of training data.

1. Install [Tailscale](https://tailscale.com/) on always-on machine + phone/laptop.
2. Run Email Swipe as a service:

```bash
# Example: fixed PORT env (serve-ui picks a free port when unset)
PORT=8765 python /path/to/email-swipe/scripts/serve-ui.py
```

3. Use **Tailscale Serve** or Funnel for HTTPS to that port.
4. Bookmark `https://your-machine.your-tailnet.ts.net` on phone → Add to Home Screen.

**Agent:** When user enables *Explore remote access* in **Advanced settings** → Access, help them verify Tailscale + service unit + URL.

---

## Option B — VPS with persistent disk

1. Provision VPS (any provider).
2. Clone repo; mount volume at e.g. `/var/lib/email-swipe`.
3. Set data dir (when supported) or symlink `~/.config/email-swipe` → volume.
4. Run agent + MCP + `serve-ui.py` on the VPS.
5. Put **Caddy** or nginx in front with HTTPS + **basic auth** (training data is sensitive).

```bash
# systemd example (simplified)
ExecStart=/usr/bin/python3 /opt/email-swipe/scripts/serve-ui.py
Environment=PORT=8765
```

6. Point Telegram bot at agent on same VPS.

---

## Option C — Cloudflare Tunnel (home server, no open ports)

1. Install `cloudflared` on machine running `serve-ui.py`.
2. Tunnel to `localhost:PORT`.
3. Optional Cloudflare Access for auth.
4. Data stays on home disk; tunnel must run while UI is needed.

---

## Option D — ngrok / quick tunnels

Good for **testing** remote phone access. URL may change on free tier. Not ideal for daily use unless you pay for a reserved domain.

---

## Option E — SSH port forward

From remote laptop:

```bash
ssh -N -L <PORT>:localhost:<PORT> user@home-server
```

Open `http://localhost:<PORT>` locally (match `PORT` from `serve-ui.py` or `runtime.json`). Works when SSH session is up; not a persistent phone bookmark.

---

## Option F — PaaS without persistence (caution)

Repo `render.yaml` is an **example only**. Ephemeral disk loses `preferences.json`, `settings.json`, and compiled artifacts on redeploy.

Only use PaaS if you attach **persistent storage** and understand you are operating infrastructure — not the default product path.

---

## Security checklist

Training data includes **sender, subject, snippets, and rules**.

- [ ] Prefer private network (Tailscale) over public internet
- [ ] If public URL: HTTPS + authentication
- [ ] Do not expose unauthenticated UI to the open web
- [ ] Rotate tunnel credentials if leaked
- [ ] Same trust model as giving an agent access to your mail

---

## PWA / home screen

Once you have a **stable HTTPS or LAN URL**:

1. Open URL in mobile Safari / Chrome.
2. **Add to Home Screen** / Install app.
3. `manifest.json` already sets `display: standalone`.

Server must stay running on the host behind the URL.

---

## Agent runbook (when user enables explore remote access)

1. Confirm goal: UI from anywhere, settings synced, agent on Telegram.
2. Ask: always-on machine at home, or VPS?
3. Recommend **same host** for agent + `serve-ui.py` + MCP.
4. Walk through chosen option (A–F) from this doc.
5. Set fixed `PORT` env var; document URL in `runtime.json`.
6. Verify: phone opens UI → swipe → Save → `get_policy_brief` shows compile.
7. Remind: Email Swipe does not provide hosting — user operates the stack.

**MCP:** `session_intake_assess` includes `access.exploreRemoteReachability` when enabled in settings.

---

## What Email Swipe does not provide

- Managed cloud hosting or `emailaiguy.com/your-ui`
- Built-in auth on `serve-ui.py` (add reverse proxy)
- Push notifications for digests (use agent / Telegram)
- Guaranteed static URL without your tunnel/DNS

---

## Related docs

- [deployment.md](./deployment.md) — Options F–G summary
- [ADVANCED-SETTINGS-SPEC.md](../docs/ADVANCED-SETTINGS-SPEC.md) — Access tab design
- [unified-inbox.md](./unified-inbox.md) — Multi-mailbox on same host
