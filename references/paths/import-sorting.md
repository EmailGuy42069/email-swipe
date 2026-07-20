# Import sorting path (no swipe UI)

**Suggest when:** The user says something like *"my inbox is already sorted — learn from my folders and make rules"* and would rather not swipe.

This path skips the swipe UI entirely. It reads how mail is already filed and
turns that into the same artifacts a swipe session produces
(`policy-graph.json`, `platform-rules.json`, `assistant-brief.md`, etc.).

## Confirm first — this is required

Existing sorting is **not** guaranteed to match current preferences:

- Folders can hold **stale or lingering mail** the user no longer wants there.
- Old habits may not reflect what they want **now**.
- One misfiled thread can teach a wrong rule.

So before you apply anything:

1. Make sure they genuinely want to **skip the swipe UI**. Offer it as a choice,
   don't assume. (`bootstrap` remains the safe default for most people.)
2. Always run a **preview** and review the plan with them.
3. Only apply after they explicitly confirm.

## Agent script

1. Intake → `session_intake_confirm import-sorting`
2. **Fetch snapshot** (Gmail via gog):

```bash
python scripts/fetch_folder_snapshot.py -o folders.json --per-folder 10
# list labels only: --list-only
# MCP: fetch_folder_snapshot
```

Or build JSON manually if mail is already in agent context:

```json
{
  "folders": [
    {"name": "Receipts",  "emails": [{"from": "billing@amazon.com", "subject": "Order shipped"}]},
    {"name": "Vendors",   "emails": [{"from": "sales@acme.io", "subject": "Quick demo?"}]},
    {"name": "Trash",     "role": "dont_keep", "emails": [{"from": "deals@spam.co", "subject": "WIN"}]},
    {"name": "Important", "role": "important",  "emails": [{"from": "boss@work.com", "subject": "Q3"}]}
  ],
  "folderPreference": "moderate"
}
```

`role` is optional — inferred from the folder name when omitted:

| Inferred role | Folder names | Becomes |
|---------------|--------------|---------|
| `dont_keep` | trash, deleted, spam, junk, bin | training action `spam` |
| `important` | important, starred, flagged, priority, vip | training action `important` |
| `keep` | inbox, keep, archive, saved | training action `keep` |
| `file` | anything else (Receipts, Vendors, …) | a **folder route** |

3. **Preview** (nothing is saved):

```bash
python scripts/learn_from_folders.py folders.json --preview
# or MCP: learn_from_folders { folders: [...], preview: true }
```

4. Read the `plan` back to the user. Each `file` folder becomes a route:
   - Name matches a built-in type → **Smart category** (receipts, newsletters, promotions, social, notifications)
   - Otherwise → **AI rule** (you judge; seeded from the folder's top domains)
   - Dominant single domain (≥3 msgs, ≥50%) → an extra **Strict domain** rule

5. On confirmation, **apply**:

```bash
python scripts/learn_from_folders.py folders.json
# or MCP: learn_from_folders { folders: [...], preview: false }
```

This writes `preferences.json` (synthetic swipes + settings with
`advancedRoutingEnabled: true`), persists settings, and compiles all artifacts.

6. Present `assistant-brief.md` and confirm/adjust the routes in chat.
7. Build the routes out in the email platform per `platform-rules.json → folderRoutes` (inbox-preserving, suggest-only).

## Notes

- Filed mail (`folderRoute`) does **not** generate spam/keep label suggestions —
  its routing lives in `folderRoutes`. Only `keep`/`important`/`dont_keep` folders
  feed the label/priority suggestions.
- The user can later open the swipe UI to refine any route (advanced settings are
  already populated from this import).

## Example agent line

> "Your inbox is already well organized. I can learn rules straight from your
> folders — no swiping. First I'll show you exactly what I'd create so we can
> drop anything that's just old mail sitting in the wrong place. Sound good?"
