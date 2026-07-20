---
name: email-swipe
description: Tinder-style email triage that trains AI on your preferences. On activation call get_skill_context (MCP) first — one UI (index.html), demo is sample mail only. Swipe don't keep/keep, double-tap important, to build a token-efficient training pack for agent inbox review.
---

# Email Swipe Skill

Primary goal: train an agent to sort an individual's inbox based on their needs. The swipe UI is a helpful training surface, not the product's purpose.

**Fast paths:** [references/QUICKSTART.md](references/QUICKSTART.md) · [AGENTS.md](AGENTS.md)

## Before anything else (prevents common agent mistakes)

**MCP connected?** Call **`get_skill_context`** first — returns activation flow, UI entry point, git-status expectations, **agent spine**, and **environment.json** (verified mail access).

**No MCP?** Read [AGENTS.md](AGENTS.md) and [references/agent-spine.md](references/agent-spine.md), or run `python scripts/session-intake.py assess`.

## Remembering skill functionality

Do **not** memorize how to open the UI or run intake in host memory. Re-call `get_skill_context` each session.

| Remember… | How |
|-----------|-----|
| Skill how-tos | Rehydrate from skill (`get_skill_context`) |
| Mail access that already works here | `environment.json` → `emailAccessByAccount[accountId]` via `record_email_access` |
| Account registry (unified inbox) | Spine `unifiedInbox.accounts` via `set_mail_accounts` |
| Live UI URL | `runtime.json` / `serve-ui.py` output |

## Agent spine (you own advanced settings)

Most advanced settings are **dormant**. Your spine is source of truth; disk/UI mirror it.

| When | MCP |
|------|-----|
| Before opening UI | `update_settings` (push spine → disk) |
| After UI / export / user saved settings | `get_agent_spine` (hydrate memory) |
| Before mail recommendations | Read `activeSections` + `policy-graph` / brief |

Full protocol: [references/agent-spine.md](references/agent-spine.md)

| Mistake | Truth |
|---------|-------|
| "Should I use demo.html?" | **No.** One UI only: `index.html` at the Desktop URL from `serve-ui.py`. |
| "Demo mode = different page?" | **No.** Demo = sample mail (`demo-emails.json`), same UI. |
| "Uncommitted changes in repo?" | **Expected.** Gitignored runtime files (`emails.json`, `settings.json`, …) — ignore them. |
| "Which port?" | **Dynamic.** Use the Desktop URL printed by `serve-ui.py` or `~/.config/email-swipe/runtime.json`. |

## On activation (required — do this first)

**Ordered phases — do not skip:**

1. `get_skill_context` (MCP) or read `AGENTS.md`
2. `check_email_access` + ask user about mail access (see [email-access-gate.md](references/email-access-gate.md)); after a successful fetch call `record_email_access` (with `accountId` per mailbox when unified inbox)
3. `session_intake_assess` → discovery → `discover` → `recommend` → user chooses → `confirm`
4. Execute path runbook → train → post-training brief

**Evaluator demo only:** `python scripts/session-intake.py demo` → `serve-ui.py` (skips intake; sample mail only).

**Real sessions — do not inject emails or start the UI until intake is confirmed and mail access is resolved (if user wants real inbox).**
**Do not treat the UI as the default goal.** Some users should go straight to `import-sorting` with no swiping at all.

### Three paths

| Path | When to suggest | What happens |
|------|-----------------|--------------|
| **bootstrap** | No rules, first training | Swipe 30–50 emails, learn from scratch |
| **calibrate** | User already has rules | Import rules → swipe only uncertain emails |
| **refine** | Prior training + gaps | Short session on weak areas |
| **import-sorting** | Inbox already sorted, prefers no UI | Learn rules from existing folders — **no swiping** |

**Path runbooks:** `references/paths/bootstrap.md`, `calibrate.md`, `refine.md`, `import-sorting.md`

**import-sorting is backend-only** (no swipe UI). Offer it early as a first-class choice, especially when the user already sorts mail into folders. Always `learn_from_folders` with `preview: true` and review with the user before applying — folders can hold stale/lingering mail or outdated choices.

**Advanced folder routing:** Unlock in **Advanced settings** → `references/paths/advanced-folders.md`

Routes support three modes: **AI rule** (plain-English + agent judgment), **Smart category** (heuristics), **Strict** (exact keyword/domain/sender). Agent should set `folderJudgments` on inject for AI rules.

Advanced routes are **persisted automatically** to `settings.json` on every compile — remember them across sessions (don't re-ask). After compile they appear in `platform-rules.json → folderRoutes[]` (with `howToBuild`) and `policy-graph.json → folderRoutingPolicies`. **Build them out** as labels/folders in the user's email platform, inbox-preserving unless the user approves a skip-inbox filter.

**Recommend based on prior knowledge** (local artifacts + agent memory), then **let the user override**.

## User experience (swipe UI)

| Gesture | Action |
|---------|--------|
| ← Left | Don't keep |
| → Right | Keep |
| Double-tap | Important |

No setup required. Optional: **Advanced settings** (agent toggle, folder routing, rhythm).

## After path is confirmed

1. Set agent name → `python scripts/setup-agent.py` (or `AGENT_NAME="YourAgent" python scripts/setup-agent.py`)
2. Build email batch for the selected path (see `intake-router.md`)
3. `python scripts/inject-emails.py /path/to/batch.json`
4. `python scripts/serve-ui.py`
5. After session: preferences auto-save **and auto-compile** when using `serve-ui.py`
6. Fetch `assistant-brief.md` via MCP or `GET /api/policy-brief` — **present the brief to the user**
7. Enter **recommendation mode** — suggest only; no auto-label or archive

Collect job context and goals **in chat** during discovery, not in the UI settings form.

## Email injection

### Agent identity (first session)

```bash
python scripts/setup-agent.py
# or: AGENT_NAME="YourAgent" python scripts/setup-agent.py
```

```bash
python scripts/inject-emails.py /path/to/batch.json
python scripts/preflight.py
python scripts/serve-ui.py
```

Batch schema: `metadata.sessionMode`, `emails[]` with `id`, `sender`, `from`, `subject`, `snippet`, `html` (strongly preferred; fetch full sanitized HTML whenever available). **Always** include `predictedAction` + `predictionConfidence` on every email (bootstrap included) — guess even when unsure. Optional `agentNote` for edge cases.

## After training (zero-download path)

When `serve-ui.py` is running, compilation happens automatically on session end.

| Delivery | How |
|----------|-----|
| **MCP** (preferred) | `python scripts/watch-preferences.py` |
| **Local API** | `GET /api/policy-brief`, `/api/training-pack`, `/api/policy-graph`, `/api/calibration` |
| **Files** | `~/.config/email-swipe/assistant-brief.md`, `policy-graph.json`, etc. |
| Export download | Last resort only |

### MCP tools

**Intake (before training):** `get_skill_context`, `check_email_access`, `record_email_access`, `session_intake_assess`, `session_intake_discover`, `session_intake_recommend`, `session_intake_confirm`, `get_intake_state`, `session_intake_demo`

**Training (after swiping or import-sorting):** `compile_training`, `get_policy_brief`, `get_policy_graph`, `get_calibration`, `get_training_pack`, `get_watch_rules`, `learn_from_folders`, `fetch_folder_snapshot`

**Settings (agent ↔ UI sync):** `get_agent_spine`, `update_settings`, `set_mail_accounts`, `get_session_status` — see [references/agent-spine.md](references/agent-spine.md)

### Manual fallback (serve-ui not used)

```bash
python scripts/compile_training.py ~/.config/email-swipe/preferences.json --save-settings
# legacy import path:
python scripts/import-preferences.py ~/Downloads/preferences.json
```

## Artifacts in `~/.config/email-swipe/`

| File | Agent use |
|------|-----------|
| `intake.json` | Discovery phase, recommended/confirmed path |
| **`assistant-brief.md`** | **Present to user** after training |
| **`policy-graph.json`** | Structured policies (default: recommend-only) |
| **`training-pack.json`** | Slim runtime slice (v3) |
| `calibration.json` | Session agreement + gaps |
| `preferences.json` | Raw swipes (archive) |
| `settings.json` | Disk mirror for UI — agent truth is **spine** (`get_agent_spine` / `update_settings`) |

## Learning architecture

```
Intake (discover → recommend → user confirms path)
    ↓
User swipes (queue depends on path)
    ↓
preferences.json → auto-compile
    ↓
assistant-brief.md + policy-graph.json
    ↓
Agent: read brief → confirm with user → recommendation mode
```

## Runbooks

- **Quickstart:** `references/QUICKSTART.md`
- **Intake:** `references/intake-router.md`
- **Post-training:** `references/post-training-flow.md`

## Optional mail scripts

See `scripts/advanced/README.md` for `fetch-emails-html.py`, `fetch-folders.py` — not required for training.

## Mail config (if fetching directly)

```bash
python scripts/setup-config.py   # EMAIL_SWIPE_EMAIL, etc.
```

## Privacy

- UI never calls email APIs
- `preferences.json` contains sender/subject snippets — treat as sensitive
- Agents should use brief + training-pack at runtime, not full swipe history in prompts
