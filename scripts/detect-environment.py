#!/usr/bin/env python3
"""
Detect available email access methods and recommend the best one.
Returns JSON with available providers and recommended approach.
"""

import json
import subprocess
import shutil
import os
import sys

def run_cmd(cmd, capture=True):
    """Run a command and return output or None if fails."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=capture, 
            text=True, 
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() if capture else True
        return None
    except:
        return None

def check_gog():
    """Check if gog CLI is available and authenticated."""
    gog_path = shutil.which("gog") or "/root/go/bin/gog"
    if not os.path.exists(gog_path):
        return None
    
    # Check if authenticated (need account flag)
    result = run_cmd(f"{gog_path} gmail labels list -a blake@blakemcginn.com 2>&1")
    if result and "error" not in result.lower() and "unauthorized" not in result.lower():
        return {
            "name": "gog",
            "path": gog_path,
            "type": "cli",
            "fetch_cmd": f"{gog_path} gmail messages list -a blake@blakemcginn.com -n 50 -j",
            "priority": 1
        }
    return None

def check_gmail_mcp():
    """Check if gmail-mcp is available."""
    if os.environ.get("GOOGLE_ACCESS_TOKEN") or os.environ.get("GMAIL_MCP_TOKEN"):
        return {
            "name": "gmail-mcp",
            "type": "mcp",
            "priority": 2
        }
    # Check if npx gmail-mcp works
    result = run_cmd("npx gmail-mcp --help 2>&1 | head -1")
    if result and "gmail" in result.lower():
        return {
            "name": "gmail-mcp",
            "type": "mcp",
            "note": "Requires GOOGLE_ACCESS_TOKEN environment variable",
            "priority": 2
        }
    return None

def check_imap():
    """Check if IMAP credentials are configured."""
    imap_env = os.environ.get("IMAP_SERVER") or os.environ.get("EMAIL_IMAP")
    if imap_env:
        return {
            "name": "imap",
            "type": "protocol",
            "priority": 3
        }
    return None

def check_msgraph():
    """Check if Microsoft Graph is available."""
    if os.environ.get("MSGRAPH_TOKEN") or os.environ.get("OUTLOOK_TOKEN"):
        return {
            "name": "msgraph",
            "type": "api",
            "priority": 2
        }
    return None

def detect_environment():
    """Detect the runtime environment."""
    env = {
        "is_vps": False,
        "has_tailscale": False,
        "cloudflare_available": shutil.which("cloudflared") is not None,
        "ssh_available": True,
        "local_access": False
    }
    
    # Check if we're on a VPS (no display, likely remote)
    if not os.environ.get("DISPLAY") and not shutil.which("gnome-shell"):
        env["is_vps"] = True
    
    # Check for tailscale
    if shutil.which("tailscale"):
        result = run_cmd("tailscale status 2>&1 | head -1")
        if result and "error" not in result.lower():
            env["has_tailscale"] = True
    
    # Check if user is local (same machine as agent)
    if os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        env["local_access"] = False  # User is SSH'd in
    elif not env["is_vps"]:
        env["local_access"] = True
    
    return env

def recommend_deployment(env):
    """Recommend deployment method based on environment."""
    if env["local_access"]:
        return {
            "method": "localhost",
            "url": "http://localhost:8765",
            "note": "User is on same machine as agent"
        }
    
    if env["has_tailscale"]:
        return {
            "method": "tailscale",
            "note": "Use tailscale IP for secure access",
            "requires": "tailscale status to get IP"
        }
    
    if env["cloudflare_available"]:
        return {
            "method": "cloudflare_tunnel",
            "cmd": "cloudflared tunnel --url http://localhost:8765",
            "note": "Creates temporary public URL (good for phones)"
        }
    
    if env["is_vps"]:
        return {
            "method": "vps_public_ip",
            "note": "VPS has public IP but may need firewall rules",
            "warning": "Port 8765 must be open in firewall"
        }
    
    return {
        "method": "ssh_tunnel",
        "cmd": "ssh -L 8765:localhost:8765 <vps-host>",
        "note": "Requires SSH access from user's machine"
    }

def main():
    providers = []
    
    # Check all email providers
    for checker in [check_gog, check_gmail_mcp, check_imap, check_msgraph]:
        result = checker()
        if result:
            providers.append(result)
    
    # Sort by priority
    providers.sort(key=lambda x: x.get("priority", 99))
    
    # Detect environment
    env = detect_environment()
    deployment = recommend_deployment(env)
    
    output = {
        "email_providers": providers,
        "recommended_provider": providers[0]["name"] if providers else None,
        "environment": env,
        "recommended_deployment": deployment,
        "ready_for_training": len(providers) > 0
    }
    
    print(json.dumps(output, indent=2))
    return 0 if providers else 1

if __name__ == "__main__":
    sys.exit(main())
