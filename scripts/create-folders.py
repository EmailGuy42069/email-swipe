#!/usr/bin/env python3
"""Create folders in Gmail from folder-requests.json."""

import json
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def create_label_gog(name):
    """Create a label in Gmail using gog CLI."""
    import subprocess
    
    gog_path = "/root/go/bin/gog"
    account = "blake@blakemcginn.com"
    
    # gog may not support label creation directly
    # This is a placeholder - actual implementation depends on gog capabilities
    cmd = [gog_path, "gmail", "labels", "create", name, "-a", account]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr if result.returncode != 0 else "Created"

def create_label_api(name):
    """Create a label using Gmail API directly."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    SERVICE_ACCOUNT_FILE = '/root/.config/gog/service-account.json'
    USER_EMAIL = 'blake@blakemcginn.com'
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES, subject=USER_EMAIL)
        service = build('gmail', 'v1', credentials=credentials)
        
        label_object = {
            'name': name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show'
        }
        
        result = service.users().labels().create(userId='me', body=label_object).execute()
        return True, result.get('id')
    except Exception as e:
        return False, str(e)

def main():
    if len(sys.argv) < 2:
        print("Usage: create-folders.py <folder-requests.json>", file=sys.stderr)
        return 1
    
    requests_file = sys.argv[1]
    
    if not os.path.exists(requests_file):
        print(f"File not found: {requests_file}", file=sys.stderr)
        return 1
    
    with open(requests_file) as f:
        data = json.load(f)
    
    folders = data.get("createFolders", [])
    
    if not folders:
        print("No folders to create", file=sys.stderr)
        return 0
    
    print(f"Creating {len(folders)} folder(s)...", file=sys.stderr)
    
    created = []
    failed = []
    
    for folder in folders:
        name = folder.get("name")
        if not name:
            continue
        
        print(f"  Creating '{name}'...", file=sys.stderr)
        
        # Try API method first
        success, result = create_label_api(name)
        
        if success:
            created.append({"name": name, "id": result})
            print(f"    ✓ Created", file=sys.stderr)
        else:
            failed.append({"name": name, "error": result})
            print(f"    ✗ Failed: {result}", file=sys.stderr)
    
    # Output results
    output = {
        "created": created,
        "failed": failed,
        "total": len(folders),
        "success": len(created)
    }
    
    print(json.dumps(output, indent=2))
    
    if failed:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
