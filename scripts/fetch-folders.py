#!/usr/bin/env python3
"""Fetch user's Gmail labels/folders for UI config."""

import subprocess
import json
import sys

GOG_PATH = "/root/go/bin/gog"
ACCOUNT = "blake@blakemcginn.com"

def fetch_labels():
    """Fetch labels from Gmail using gog."""
    result = subprocess.run(
        [GOG_PATH, "gmail", "labels", "list", "-a", ACCOUNT, "-j"],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        return None
    
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else data.get("labels", [])
    except json.JSONDecodeError:
        print(f"Failed to parse: {result.stdout}", file=sys.stderr)
        return None

def map_to_folders(labels):
    """Map Gmail labels to UI folder format."""
    # System labels to exclude
    exclude = {"INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "UNREAD", "CATEGORY_PERSONAL", 
               "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}
    
    default_folders = [
        {"id": "spam", "label": "Spam", "icon": "🗑️", "color": "#ef4444"},
        {"id": "archive", "label": "Archive", "icon": "🗄️", "color": "#6b7280"},
        {"id": "keep", "label": "Keep", "icon": "✓", "color": "#10b981"},
        {"id": "important", "label": "Important", "icon": "⭐", "color": "#f59e0b"},
    ]
    
    custom_folders = []
    icon_map = {
        "receipt": "🧾",
        "work": "💼",
        "newsletter": "📰",
        "travel": "✈️",
        "finance": "💰",
        "social": "💬",
        "shopping": "🛍️",
    }
    
    for label in labels:
        name = label.get("name", "")
        if name in exclude or name.startswith("CATEGORY_"):
            continue
        
        # Determine icon based on name
        icon = "📁"
        for keyword, ic in icon_map.items():
            if keyword.lower() in name.lower():
                icon = ic
                break
        
        folder_id = name.lower().replace(" ", "-").replace("/", "-")
        custom_folders.append({
            "id": folder_id,
            "label": name,
            "icon": icon,
            "color": "#6366f1"
        })
    
    # Combine: defaults first, then custom
    return default_folders + custom_folders

def main():
    labels = fetch_labels()
    if labels is None:
        # Return defaults on error
        print(json.dumps({
            "folders": [
                {"id": "spam", "label": "Spam", "icon": "🗑️", "color": "#ef4444"},
                {"id": "archive", "label": "Archive", "icon": "🗄️", "color": "#6b7280"},
                {"id": "keep", "label": "Keep", "icon": "✓", "color": "#10b981"},
                {"id": "important", "label": "Important", "icon": "⭐", "color": "#f59e0b"},
            ]
        }, indent=2))
        return 1
    
    folders = map_to_folders(labels)
    config = {"folders": folders}
    
    # Output to stdout
    print(json.dumps(config, indent=2))
    
    # Also save to UI directory
    import os
    ui_dir = os.path.join(os.path.dirname(__file__), "../assets/ui")
    os.makedirs(ui_dir, exist_ok=True)
    config_path = os.path.join(ui_dir, "config.json")
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"Saved to {config_path}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
