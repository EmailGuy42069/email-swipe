# Agent spine — settings source of truth

**Read this with the skill.** The agent spine is how *you* (the agent) remember Email Swipe advanced settings. The UI and `~/.config/email-swipe/settings.json` are **mirrors** for the human — not your memory.

Most advanced settings are **dormant** (unused) for any given user. Only activate and reason about sections that are explicitly on or that the user discussed.

---

## Principle

| Layer | Role |
|-------|------|
| **Agent spine** | Source of truth for your behavior and for what you tell the user |
| **`settings.json` on disk** | Mirror so the UI shows the same values when `serve-ui.py` runs |
| **UI `localStorage`** | Browser cache only — never trust over spine or disk after sync |
| **`preferences.json`** | Swipe export input to compile — may embed settings snapshot at session end |

You own the spine. Disk follows you when opening the UI; you follow disk when the user changed settings in the UI.

---

## Three loops (memorize these)

### 1. Before opening the UI — **push spine → UI**

When you start `serve-ui.py` or ask the user to open Advanced settings:

1. Ensure your spine reflects the latest from chat and prior sessions.
2. **`update_settings`** with your spine's `settings` object (partial patch is fine).
3. Start or confirm `serve-ui.py` is running.
4. Give the user the **Desktop URL** from server output or `runtime.json`.

The user must see *your* settings in the UI, not stale defaults.

### 2. After UI feedback — **hydrate spine ← UI**

When the user finishes swiping, saves Advanced settings, exports, or reports what they changed:

1. **`get_settings`** (one call — includes settings, accounts status, intake, session).
2. Merge into your spine. Update which sections are **active** vs **dormant**.
3. Do **not** re-ask the user for dormant fields you already have.
4. If compile ran, also **`get_policy_brief`** / **`get_session_status`** as needed for post-training.

### 3. Before acting on mail — **read spine only**

When recommending labels, digests, autonomy, multi-inbox routing, etc.:

1. Check **`activeSections`** on your spine — if a section is dormant, ignore it.
2. Use **`policy-graph.json`**, **`training-pack.json`**, and **`assistant-brief.md`** for trained rules (compiled artifacts).
3. Never invent settings from memory if you have not hydrated since the last UI session.

---

## Tool routing (no alternatives)

| Intent | Tool | Notes |
|--------|------|--------|
| Read full mirror + status | **`get_settings`** | Default read. Includes `settings`, `accountsStatus`, `intake`, `runtime`, `sessionStatus`. |
| Read spine-shaped view | **`get_agent_spine`** | Same data, plus `activeSections` / `dormantSections`. Prefer on activation and after UI. |
| Write spine → disk/UI | **`update_settings`** | Partial patch. Use before opening UI. `compile: true` only when preferences exist and policy must refresh. |
| Register mailboxes | **`set_mail_accounts`** | Then merge result into spine; mark `unifiedInbox` active. |
| Intake phase only | `get_intake_state` | Optional; `get_settings.intake` usually enough. |
| Accounts list only | `list_mail_accounts` | Optional; `get_settings` usually enough. |

**Do not** read `assets/ui/settings.json`, browser storage, or repo copies for truth.

---

## Dormant by default

These sections start **dormant** until the user or you explicitly turn them on:

| Section | Becomes active when |
|---------|---------------------|
| `agent` (name) | You set a name in setup or user asks to name the agent |
| `agent.postTraining` | `agent.enabled` is true (user wants inbox review help after training) |
| `unifiedInbox` | `unifiedInbox.enabled` is true |
| `sorting.advanced` | `folders.advancedRoutingEnabled` is true |
| `rules.autonomy` | `agent.autonomyLevel` is not `recommend` |
| `rules.platform` | User discussed platform rules or changed forbidden actions |
| `rhythm` | User asked for digest cadence or changed scan frequency from default |
| `access.remote` | `access.exploreRemoteReachability` is true |
| `context` | `context.problemToSolve` or `context.notes` is non-empty |

**Never prompt** for calendar, life story, projects, or relationships in Email Swipe — that lives in your general user context, not this spine.

---

## Spine shape (keep in agent memory)

```json
{
  "settings": { },
  "activeSections": ["agent"],
  "dormantSections": ["unifiedInbox", "sorting.advanced", "rules.autonomy", "rhythm", "access.remote", "context"],
  "lastSync": {
    "from": "chat | ui | disk",
    "at": "ISO-8601 or null"
  }
}
```

`get_agent_spine` returns this structure hydrated from disk. After merging user chat, update your in-memory copy, then `update_settings` before the UI.

---

## Common mistakes

| Mistake | Correct |
|---------|---------|
| User opens UI without you pushing settings | `update_settings` first |
| User changed Rhythm in UI; you still use old cadence | `get_agent_spine` after session |
| Re-ask for unified inbox when dormant | Skip unless user mentions multiple accounts |
| `list_mail_accounts` then forget `get_settings` | One `get_agent_spine` after UI |
| Treat `compile` from preferences as spine truth | Preferences embed settings at compile time — hydrate after |
| Execute rhythm (cron/push) yourself | Rhythm is instructions for you in chat only |

---

## Related docs

- [ADVANCED-SETTINGS-SPEC.md](../docs/ADVANCED-SETTINGS-SPEC.md) — what each tab means (human UI)
- [unified-inbox.md](./unified-inbox.md) — multi-mailbox policy
- [autonomy-levels.md](./autonomy-levels.md) — autonomy tiers
- [post-training-flow.md](./post-training-flow.md) — after compile
