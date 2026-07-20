#!/usr/bin/env python3
"""Fetch user's Gmail labels/folders for UI config."""

import subprocess
import json
import sys
import os
import argparse

from email_config import ConfigError, get_email_account, get_gog_path, load_config

DEFAULT_FOLDERS = [
    {"id": "spam", "label": "Spam", "color": "#b42318"},
    {"id": "archive", "label": "Archive", "color": "#667085"},
    {"id": "keep", "label": "Keep", "color": "#027a48"},
    {"id": "important", "label": "Important", "color": "#b54708"},
]


def fetch_labels():
    """Fetch labels from Gmail using gog."""
    cfg = load_config()
    gog_path = get_gog_path(cfg)
    if not gog_path:
        print("gog CLI not found. Set EMAIL_SWIPE_GOG_PATH or install gog.", file=sys.stderr)
        return None

    try:
        account = get_email_account(cfg)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return None

    result = subprocess.run(
        [gog_path, "gmail", "labels", "list", "-a", account, "-j"],
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
    exclude = {"INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "UNREAD", "CATEGORY_PERSONAL",
               "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"}

    custom_folders = []
    color_map = {
        "receipt": "#175cd3",
        "work": "#344054",
        "newsletter": "#5925dc",
        "travel": "#0e7090",
        "finance": "#027a48",
        "social": "#444ce7",
        "shopping": "#c11574",
    }

    for label in labels:
        name = label.get("name", "")
        if name in exclude or name.startswith("CATEGORY_"):
            continue

        color = "#475467"
        for keyword, c in color_map.items():
            if keyword.lower() in name.lower():
                color = c
                break

        folder_id = name.lower().replace(" ", "-").replace("/", "-")
        custom_folders.append({
            "id": folder_id,
            "label": name,
            "color": color
        })

    return DEFAULT_FOLDERS + custom_folders


def main():
    parser = argparse.ArgumentParser(description="Fetch Gmail labels for UI folders")
    parser.add_argument("--account", "-a", help="Email account (overrides config)")
    args = parser.parse_args()

    if args.account:
        os.environ["EMAIL_SWIPE_EMAIL"] = args.account

    labels = fetch_labels()
    if labels is None:
        print(json.dumps({"folders": DEFAULT_FOLDERS}, indent=2))
        return 1

    folders = map_to_folders(labels)
    config = {"folders": folders}

    print(json.dumps(config, indent=2))

    ui_dir = os.path.join(os.path.dirname(__file__), "../assets/ui")
    os.makedirs(ui_dir, exist_ok=True)
    config_path = os.path.join(ui_dir, "config.json")

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Saved to {config_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
