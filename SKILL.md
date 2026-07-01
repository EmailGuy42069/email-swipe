---
name: email-swipe
description: Tinder-style email triage UI with drag-and-drop sorting. Auto-detects email access, adapts to user's personal folders, and supports folder creation. Use when user wants to (1) train AI on email preferences with custom folders, (2) sort emails with full HTML preview, (3) create new email folders from the UI.
---

# Email Swipe Skill

Full-screen email cards with **simple 3-action mode** (Archive/Spam/Keep) and **advanced drag-and-drop** with personal folders.

## Quick Start

### Step 1: Detect Environment & Fetch Folders

```bash
python3 scripts/detect-environment.py
```

This detects:
- Email provider (gog, gmail-mcp, etc.)
- User's personal Gmail folders/labels
- Deployment environment

### Step 2: Fetch Emails + Folders

```bash
# Fetch emails with HTML content
python3 scripts/fetch-emails-html.py --limit 50

# Fetch user's personal folders
python3 scripts/fetch-folders.py
```

### Step 3: Configure UI with Personal Folders

The agent must inject the user's folders into the UI. Create `assets/ui/config.json`:

```json
{
  "folders": [
    { "id": "spam", "label": "Spam", "icon": "🗑️", "color": "#ef4444" },
    { "id": "archive", "label": "Archive", "icon": "🗄️", "color": "#6b7280" },
    { "id": "keep", "label": "Keep", "icon": "✓", "color": "#10b981" },
    { "id": "important", "label": "Important", "icon": "⭐", "color": "#f59e0b" },
    { "id": "receipts", "label": "Receipts", "icon": "🧾", "color": "#3b82f6" },
    { "id": "newsletters", "label": "Newsletters", "icon": "📰", "color": "#8b5cf6" }
  ]
}
```

**Include the user's actual Gmail labels** in the folders list.

### Step 4: Start UI

```bash
python3 scripts/serve-ui.py
```

### Step 5: After User Exports

Check for folder creation requests:

```bash
# User export includes preferences.json AND folder-requests.json
python3 scripts/import-preferences.py ~/Downloads/preferences.json

# Create requested folders in Gmail
python3 scripts/create-folders.py ~/Downloads/folder-requests.json
```

## UI Modes

### Normal Mode (Default)
- Full-screen email cards with HTML rendering
- **3 actions**: ← Archive | ↑ Spam | → Keep
- Swipe gestures on mobile
- Tap actions at bottom

### Advanced Mode (⚙️ button)
- Slide-up panel with **all personal folders**
- Drag-and-drop or tap to sort
- **"Create New Folder"** button
- User can request custom folders

## Folder Management

### Fetching User's Folders

Use `scripts/fetch-folders.py`:

```python
#!/usr/bin/env python3
import subprocess
import json

result = subprocess.run(
    ["/root/go/bin/gog", "gmail", "labels", "list", "-a", "blake@blakemcginn.com", "-j"],
    capture_output=True, text=True
)
labels = json.loads(result.stdout)

# Map to UI folder format
folders = []
for label in labels:
    name = label.get('name', '')
    if name in ['INBOX', 'SENT', 'DRAFT', 'TRASH', 'SPAM']:
        continue
    folders.append({
        "id": name.lower().replace(' ', '-'),
        "label": name,
        "icon": "📁",
        "color": "#6366f1"
    })

print(json.dumps(folders, indent=2))
```

### Creating Folders

When export includes `folder-requests.json`:

```bash
python3 scripts/create-folders.py folder-requests.json
```

This creates the folders in Gmail via API.

## Agent Workflow

1. **"Let me fetch your emails and folders..."**
   ```bash
   python3 scripts/fetch-emails-html.py --limit 50
   python3 scripts/fetch-folders.py > assets/ui/config.json
   ```

2. **"Starting UI with your folders..."**
   ```bash
   python3 scripts/serve-ui.py
   ```

3. **User sorts emails, may request new folders**

4. **After export:**
   - Import preferences
   - Check for folder-requests.json
   - Create any requested folders
   - Confirm with user

## Export Format

### preferences.json
```json
{
  "metadata": { "version": "1.4", "totalSwipes": 25 },
  "folders": ["spam", "archive", "keep", "receipts", "newsletters"],
  "swipes": [...],
  "senderRules": {...}
}
```

### folder-requests.json (if user created folders)
```json
{
  "createFolders": [
    { "name": "Work 2024", "requestedAt": "2026-07-01T11:30:00Z" },
    { "name": "Travel Plans", "requestedAt": "2026-07-01T11:35:00Z" }
  ]
}
```

## Architecture

```
User's Gmail
    ↓
[fetch-emails-html.py] → emails.json (with HTML)
[fetch-folders.py] → config.json (personal folders)
    ↓
[serve-ui.py] → Serves UI with config
    ↓
User swipes in Normal mode OR Advanced drag-and-drop
    ↓
User may click "Create New Folder"
    ↓
User exports → preferences.json + folder-requests.json
    ↓
[import-preferences.py] → ~/.config/email-swipe/
[create-folders.py] → Creates folders in Gmail
    ↓
Agent uses preferences for future email triage
```

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `detect-environment.py` | Detect email provider and deployment |
| `fetch-emails-html.py` | Fetch emails with full HTML content |
| `fetch-folders.py` | Fetch user's Gmail labels/folders |
| `serve-ui.py` | Serve UI with config |
| `import-preferences.py` | Import exported preferences |
| `create-folders.py` | Create requested folders in Gmail |

## UI Files

| File | Purpose |
|------|---------|
| `assets/ui/index.html` | Main UI |
| `assets/ui/app.js` | Logic (Normal/Advanced modes, notes) |
| `assets/ui/styles.css` | Dark theme, full-screen cards |
| `assets/ui/config.json` | User's personal folders (agent-created) |
| `assets/ui/emails.json` | Email data (agent-created) |
