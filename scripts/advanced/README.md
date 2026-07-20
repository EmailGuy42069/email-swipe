# Optional advanced scripts

These are **not** part of the default training flow.

## Default compile path (use this)

1. User swipes in the UI (`serve-ui.py` → Desktop URL)
2. Session end or **Export** → `POST /api/preferences` → auto-compile
3. Or manually: `python scripts/compile_training.py ~/.config/email-swipe/preferences.json --save-settings`

Artifacts land in `~/.config/email-swipe/`. See `python scripts/print_state.py` for what exists.

## Legacy scripts (avoid in new docs)

| Script | Status | Use instead |
|--------|--------|-------------|
| `export-preferences.py` | Legacy | UI Export + `compile_training.py` |
| `import-preferences.py` | Advanced import | `compile_training.py` |
| `analyze-preferences.py` | Internal module / CLI | `compile_training.py` |

## Optional mail / folder tools

| Script | Purpose |
|--------|---------|
| `fetch_folder_snapshot.py` | **import-sorting** — pull labels + sample mail per folder for `learn_from_folders` |
| `fetch-folders.py` | Pull Gmail labels into `config.json` |
| `create-folders.py` | Create labels from requests |
| `fetch-emails-html.py` | Fetch inbox with HTML via Gmail API |
| `fetch-emails.py` | Experimental gog helper — not recommended for training |
