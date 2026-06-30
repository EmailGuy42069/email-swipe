#!/usr/bin/env python3
"""MCP server that watches preferences file for changes"""
import json
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / '.config' / 'email-swipe' / 'preferences.json'


def read_preferences() -> dict:
    if not CONFIG_FILE.exists():
        return {'error': 'No preferences file found. Export from the UI first.'}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def handle_request(request: dict) -> dict:
    method = request.get('method', '')
    req_id = request.get('id')

    if method == 'initialize':
        return {
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'email-swipe-preferences', 'version': '1.0.0'},
            },
        }

    if method == 'tools/list':
        return {
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'tools': [
                    {
                        'name': 'get_email_preferences',
                        'description': 'Get learned email triage preferences from swipe training data',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_sender_rules',
                        'description': 'Get per-sender email handling rules learned from swipes',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                ],
            },
        }

    if method == 'tools/call':
        params = request.get('params', {})
        tool_name = params.get('name', '')

        prefs = read_preferences()
        if 'error' in prefs:
            return {
                'jsonrpc': '2.0',
                'id': req_id,
                'result': {'content': [{'type': 'text', 'text': prefs['error']}], 'isError': True},
            }

        if tool_name == 'get_email_preferences':
            text = json.dumps(prefs, indent=2)
        elif tool_name == 'get_sender_rules':
            text = json.dumps(prefs.get('senderRules', {}), indent=2)
        else:
            return {
                'jsonrpc': '2.0',
                'id': req_id,
                'error': {'code': -32601, 'message': f'Unknown tool: {tool_name}'},
            }

        return {
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {'content': [{'type': 'text', 'text': text}]},
        }

    return {
        'jsonrpc': '2.0',
        'id': req_id,
        'error': {'code': -32601, 'message': f'Method not found: {method}'},
    }


def run_stdio_server():
    """Minimal MCP stdio server for email preferences."""
    print('Email Swipe MCP server starting (stdio)', file=sys.stderr)
    print(f'Watching: {CONFIG_FILE}', file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            continue


if __name__ == '__main__':
    run_stdio_server()
