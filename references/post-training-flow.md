# Post-training flow (agent runbook)

After the user finishes swiping, your job is to **cement** what they taught — not jump straight into inbox automation.

## Automatic compile (preferred)

When `serve-ui.py` is running, finishing a session POSTs to `/api/preferences` and auto-compiles all artifacts under `~/.config/email-swipe/`:

| Artifact | How to fetch |
|----------|----------------|
| `assistant-brief.md` | MCP `get_policy_brief` or `GET /api/policy-brief` |
| `policy-graph.json` | MCP `get_policy_graph` or `GET /api/policy-graph` |
| `calibration.json` | MCP `get_calibration` or `GET /api/calibration` |
| `training-pack.json` | MCP `get_training_pack` or `GET /api/training-pack` |

**Do not ask the user to export or run `import-preferences.py` if serve-ui handled the session.**

## Cementing conversation (5 minutes)

1. **Fetch the brief** — `get_policy_brief` (or read `assistant-brief.md`).
2. **Read it aloud in plain language** — policies, important senders, gaps, autonomy level.
3. **Confirm with the user:**
   - "Does this match how you want mail handled?"
   - "Any sender or domain I got wrong?"
   - "Anything missing you care about?"
4. **Note corrections** — if they disagree, log it in chat; optional follow-up swipe session for inconsistent senders flagged in calibration.
5. **State autonomy explicitly:** recommend-only today. No labels, archive, or send without approval.
6. **Enter recommendation mode** — for new mail, suggest actions; never auto-apply platform filters.

## MCP setup (Cursor)

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

Tools: `get_skill_context`, `get_agent_spine`, `update_settings`, `compile_training`, `get_policy_brief`, `get_policy_graph`, `get_calibration`, `get_training_pack`, `get_watch_rules`, `get_session_status`, `learn_from_folders`, `fetch_folder_snapshot`, `session_intake_demo`

## File-watcher fallback

If not using serve-ui:

```bash
python scripts/watch-preferences.py --watch
```

Recompiles when `preferences.json` changes.

## Manual fallback

```bash
python scripts/compile_training.py ~/.config/email-swipe/preferences.json --save-settings
# legacy:
python scripts/import-preferences.py ~/.config/email-swipe/preferences.json
```

## Runtime rules

- Default `autonomyLevel` on every policy: **recommend**
- Platform rules: suggest-only labels — inbox preserved
- Needs Attention: agent-managed watchlist, not hard filters
- Token budget: brief + slim training-pack at runtime; full policy-graph for tool calls

## Example brief

See `references/assistant-brief.example.md` for the format users should see after training.
