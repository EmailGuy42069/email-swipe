#!/usr/bin/env python3
"""MCP server — training artifacts + policy brief/graph/calibration."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_folder_snapshot as ffs  # noqa: E402
import learn_from_folders as lff  # noqa: E402
from agent_context import build_agent_context  # noqa: E402
from agent_spine import build_agent_spine  # noqa: E402
from email_access_gate import build_email_access_status  # noqa: E402
from environment_state import (  # noqa: E402
    clear_verified_access,
    record_verified_access,
)
from compile_training import compile_training  # noqa: E402
from email_config import ConfigError, get_email_account, get_gog_path, load_config  # noqa: E402
from session_state import build_session_status  # noqa: E402
from script_imports import session_intake_mod as intake  # noqa: E402
from settings import USER_DIR, load_settings, build_settings_api_payload, update_settings  # noqa: E402
from accounts import list_accounts, merge_accounts, unified_inbox_config  # noqa: E402

TRAINING_PACK = USER_DIR / 'training-pack.json'
POLICY_BRIEF = USER_DIR / 'assistant-brief.md'
POLICY_GRAPH = USER_DIR / 'policy-graph.json'
CALIBRATION = USER_DIR / 'calibration.json'
PREFS_FILE = USER_DIR / 'preferences.json'


def ensure_compiled() -> dict | None:
    """Compile if prefs exist but artifacts are missing or stale."""
    if not PREFS_FILE.exists():
        return None
    needs_compile = not TRAINING_PACK.exists() or not POLICY_BRIEF.exists()
    if not needs_compile and PREFS_FILE.stat().st_mtime > TRAINING_PACK.stat().st_mtime:
        needs_compile = True
    if needs_compile:
        result = compile_training(PREFS_FILE, USER_DIR, save_settings_from_prefs=True)
        if not result.get('ok'):
            return {'error': result.get('error', 'compile failed')}
    return None


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def load_training_pack() -> dict:
    err = ensure_compiled()
    if err:
        return err
    if TRAINING_PACK.exists():
        return load_json(TRAINING_PACK)
    return {'error': 'No training data. Run serve-ui.py and complete a swipe session.'}


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
                'serverInfo': {'name': 'email-swipe-training', 'version': '3.0.0'},
            },
        }

    if method == 'tools/list':
        return {
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'tools': [
                    {
                        'name': 'check_email_access',
                        'description': (
                            'Detect mail connectors (gog, Gmail API, IMAP, Graph) and return '
                            'setup guidance plus persisted environment.json. Run during discovery '
                            'before real-mail inject. If skipRediscovery is true, reuse method/fetchHint '
                            'and only confirm real vs demo. Always ask about MCP mail when detect is empty '
                            'and access is not yet verified on disk.'
                        ),
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'record_email_access',
                        'description': (
                            'Persist verified mail access to ~/.config/email-swipe/environment.json '
                            'after a successful fetch (or confirmed MCP/manual batch). '
                            'For unified inbox, pass accountId (slug from set_mail_accounts). '
                            'Omit accountId for single-inbox (_default). '
                            'Required: method. Optional: accountId, provider, address, fetchHint, notes.'
                        ),
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'accountId': {
                                    'type': 'string',
                                    'description': 'Unified inbox account slug (e.g. work-gmail)',
                                },
                                'method': {
                                    'type': 'string',
                                    'description': 'gog, gmail-mcp, imap, msgraph, manual-batch, …',
                                },
                                'provider': {'type': 'string'},
                                'address': {
                                    'type': 'string',
                                    'description': 'Email address for this account',
                                },
                                'account': {
                                    'type': 'string',
                                    'description': 'Deprecated alias for address',
                                },
                                'fetchHint': {
                                    'type': 'string',
                                    'description': 'Command or tool pattern that successfully fetched mail',
                                },
                                'notes': {'type': 'string'},
                                'clear': {
                                    'type': 'boolean',
                                    'description': 'If true, clear verified access instead of recording',
                                },
                                'clearAccountId': {
                                    'type': 'string',
                                    'description': 'When clear=true, clear only this accountId (omit to clear all)',
                                },
                            },
                            'required': [],
                        },
                    },
                    {
                        'name': 'get_skill_context',
                        'description': (
                            'Call FIRST on skill activation. Returns canonical UI entry point, '
                            'demo vs real session flow, git-status expectations, agent spine, '
                            'and environment.json (verified mail access). '
                            'Never memorize skill how-tos — rehydrate this every session.'
                        ),
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'compile_training',
                        'description': 'Force recompile from latest preferences.json into all training artifacts',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_training_pack',
                        'description': 'Get slim training-pack.json runtime slice (v3)',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_policy_brief',
                        'description': 'Get human-readable assistant-brief.md — present to user after training',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_policy_graph',
                        'description': 'Get structured policy-graph.json with autonomy levels',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_calibration',
                        'description': 'Get calibration.json — per-category agreement and inconsistency flags',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_session_status',
                        'description': 'Get runtime/completion state, recent score history, and score trend',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_agent_spine',
                        'description': (
                            'Preferred read for advanced settings. Returns agent spine: settings mirror, '
                            'activeSections vs dormantSections, accounts, intake, runtime. '
                            'Call after UI feedback; compare to your in-memory spine. '
                            'See references/agent-spine.md.'
                        ),
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'get_settings',
                        'description': (
                            'Raw settings mirror from disk (same payload as GET /api/settings). '
                            'Prefer get_agent_spine for agent behavior — includes active/dormant sections.'
                        ),
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'update_settings',
                        'description': (
                            'Push agent spine → disk/UI mirror. Merge partial patch into '
                            '~/.config/email-swipe/settings.json. Call BEFORE opening the UI. '
                            'Set compile=true only when preferences.json exists and policy must refresh. '
                            'See references/agent-spine.md.'
                        ),
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'settings': {
                                    'type': 'object',
                                    'description': 'Partial settings patch (agent, rhythm, platformRules, context, …)',
                                },
                                'compile': {
                                    'type': 'boolean',
                                    'description': 'Recompile training artifacts after save (default false)',
                                },
                            },
                        },
                    },
                    {
                        'name': 'list_mail_accounts',
                        'description': (
                            'List registered mailboxes when unified inbox is enabled. '
                            'Prefer get_agent_spine for full context. Use set_mail_accounts to register.'
                        ),
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'set_mail_accounts',
                        'description': (
                            'Replace unified inbox account registry (requires unifiedInbox.enabled). '
                            'Pass accounts[] with id, label, provider, optional address/role/connectorHint.'
                        ),
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'enabled': {'type': 'boolean'},
                                'accounts': {
                                    'type': 'array',
                                    'items': {'type': 'object'},
                                },
                            },
                        },
                    },
                    {
                        'name': 'get_watch_rules',
                        'description': 'Get agent watch rules for Needs Attention inbox review',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'session_intake_assess',
                        'description': 'Start intake: scan local artifacts and return discovery questions (run before training)',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'session_intake_discover',
                        'description': 'Save discovery answers from chat before recommending a path',
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'answers': {
                                    'type': 'object',
                                    'description': 'Discovery answers, e.g. hasExistingRules, rulesSource, goal, demoFirst',
                                },
                            },
                        },
                    },
                    {
                        'name': 'session_intake_recommend',
                        'description': 'Recommend bootstrap/calibrate/refine path with rationale and all options',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'session_intake_confirm',
                        'description': 'Lock user-selected path after they choose (required before inject-emails)',
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'path': {
                                    'type': 'string',
                                    'enum': ['bootstrap', 'calibrate', 'refine', 'import-sorting'],
                                },
                            },
                            'required': ['path'],
                        },
                    },
                    {
                        'name': 'get_intake_state',
                        'description': 'Get current intake.json phase, discovery, and confirmed path',
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'session_intake_demo',
                        'description': (
                            'Evaluator shortcut: confirm bootstrap path and inject demo emails into '
                            'emails.json. Same index.html UI via serve-ui.py — not a separate demo page. '
                            'Skips full intake — use only for demos, not real training.'
                        ),
                        'inputSchema': {'type': 'object', 'properties': {}},
                    },
                    {
                        'name': 'fetch_folder_snapshot',
                        'description': (
                            'Fetch Gmail labels + sample mail per folder for import-sorting. '
                            'Requires gog CLI. Output feeds learn_from_folders.'
                        ),
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'perFolder': {'type': 'number', 'description': 'Max emails per folder (default 10)'},
                                'listOnly': {'type': 'boolean', 'description': 'List label names only'},
                                'labels': {
                                    'type': 'string',
                                    'description': 'Comma-separated folder names to include',
                                },
                            },
                        },
                    },
                    {
                        'name': 'learn_from_folders',
                        'description': (
                            'No-UI path: learn routing rules from the user\'s existing folder sorting. '
                            'ALWAYS call with preview=true first and review the plan with the user before '
                            'applying (preview=false), since folders may hold stale/lingering mail.'
                        ),
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'folders': {
                                    'type': 'array',
                                    'description': (
                                        'Folder snapshot: [{name, role?, emails:[{from, subject, snippet?}]}]. '
                                        'role is keep|important|dont_keep|file (inferred from name if omitted).'
                                    ),
                                    'items': {'type': 'object'},
                                },
                                'folderPreference': {
                                    'type': 'string',
                                    'enum': ['minimal', 'moderate', 'many'],
                                },
                                'preview': {
                                    'type': 'boolean',
                                    'description': 'true = report plan without writing (default true).',
                                },
                            },
                            'required': ['folders'],
                        },
                    },
                ],
            },
        }

    if method == 'tools/call':
        params = request.get('params', {})
        tool_name = params.get('name', '')

        if tool_name == 'get_skill_context':
            return _tool_result(req_id, json.dumps(build_agent_context(), indent=2))

        if tool_name == 'check_email_access':
            return _tool_result(req_id, json.dumps(build_email_access_status(), indent=2))

        if tool_name == 'record_email_access':
            args_obj = params.get('arguments') or {}
            if args_obj.get('clear'):
                env = clear_verified_access(
                    account_id=args_obj.get('clearAccountId') or args_obj.get('accountId'),
                    reason=args_obj.get('notes') or args_obj.get('reason'),
                )
                return _tool_result(req_id, json.dumps(env, indent=2))
            method = args_obj.get('method')
            if not method:
                return _tool_error(req_id, 'method is required (or set clear: true)')
            try:
                env = record_verified_access(
                    method=method,
                    account_id=args_obj.get('accountId') or args_obj.get('account_id'),
                    provider=args_obj.get('provider'),
                    address=args_obj.get('address') or args_obj.get('account'),
                    fetch_hint=args_obj.get('fetchHint') or args_obj.get('fetch_hint'),
                    notes=args_obj.get('notes'),
                    source='mcp',
                )
            except ValueError as exc:
                return _tool_error(req_id, str(exc))
            return _tool_result(req_id, json.dumps(env, indent=2))

        if tool_name == 'compile_training':
            if not PREFS_FILE.exists():
                return _tool_error(req_id, 'No preferences.json — complete a swipe session first')
            result = compile_training(PREFS_FILE, USER_DIR, save_settings_from_prefs=True)
            text = json.dumps(result, indent=2)
            return _tool_result(req_id, text, is_error=not result.get('ok'))

        if tool_name == 'session_intake_assess':
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                intake.cmd_assess(argparse.Namespace())
            return _tool_result(req_id, buf.getvalue())

        if tool_name == 'session_intake_discover':
            args_obj = params.get('arguments', {})
            answers = json.dumps(args_obj.get('answers', args_obj))
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            ns = argparse.Namespace(answers=answers)
            with redirect_stdout(buf):
                intake.cmd_discover(ns)
            return _tool_result(req_id, buf.getvalue())

        if tool_name == 'session_intake_recommend':
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                intake.cmd_recommend(argparse.Namespace())
            return _tool_result(req_id, buf.getvalue())

        if tool_name == 'session_intake_confirm':
            path = params.get('arguments', {}).get('path', '')
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            ns = argparse.Namespace(path=path)
            with redirect_stdout(buf):
                code = intake.cmd_confirm(ns)
            if code != 0:
                return _tool_result(req_id, buf.getvalue(), is_error=True)
            return _tool_result(req_id, buf.getvalue())

        if tool_name == 'get_intake_state':
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                intake.cmd_get(argparse.Namespace())
            return _tool_result(req_id, buf.getvalue())

        if tool_name == 'session_intake_demo':
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = intake.cmd_demo(argparse.Namespace())
            if code != 0:
                return _tool_result(req_id, buf.getvalue(), is_error=True)
            return _tool_result(req_id, buf.getvalue())

        if tool_name == 'fetch_folder_snapshot':
            import fetch_folder_snapshot as ffs
            args_obj = params.get('arguments', {})
            cfg = load_config()
            gog_path = get_gog_path(cfg)
            if not gog_path:
                return _tool_error(req_id, 'gog CLI not found — see references/email-access.md')
            try:
                account = get_email_account(cfg)
            except ConfigError as exc:
                return _tool_error(req_id, str(exc))
            if args_obj.get('listOnly'):
                labels = ffs.fetch_labels(gog_path, account)
                names = [l.get('name', '') for l in labels if l.get('name')]
                return _tool_result(req_id, json.dumps({'account': account, 'labels': names}, indent=2))
            label_filter = None
            if args_obj.get('labels'):
                label_filter = [s.strip() for s in str(args_obj['labels']).split(',')]
            snapshot = ffs.build_snapshot(
                gog_path,
                account,
                per_folder=int(args_obj.get('perFolder', 10)),
                include_system=True,
                label_filter=label_filter,
            )
            return _tool_result(req_id, json.dumps(snapshot, indent=2))

        if tool_name == 'learn_from_folders':
            args_obj = params.get('arguments', {})
            folders = args_obj.get('folders') or []
            if not folders:
                return _tool_error(req_id, 'No folders provided')
            preview = args_obj.get('preview', True)
            folder_pref = args_obj.get('folderPreference', 'moderate')
            built = lff.build_plan(folders, folder_pref)
            route_count = sum(1 for r in built['settings']['folders']['routes'] if not r.get('action'))
            out = {
                'foldersAnalyzed': len(built['plan']),
                'emailsAnalyzed': len(built['swipes']),
                'folderRoutesLearned': route_count,
                'plan': built['plan'],
                'preview': bool(preview),
            }
            if preview:
                out['ok'] = True
                out['caution'] = (
                    'PREVIEW ONLY — nothing saved. Confirm with the user before applying: '
                    'preferences may have changed and folders can hold stale/lingering mail. '
                    'Call again with preview=false to commit.'
                )
                return _tool_result(req_id, json.dumps(out, indent=2))
            preferences = lff.build_preferences(built)
            PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PREFS_FILE, 'w') as f:
                json.dump(preferences, f, indent=2)
                f.write('\n')
            result = compile_training(PREFS_FILE, USER_DIR, save_settings_from_prefs=True)
            out['ok'] = result.get('ok', False)
            out['compile'] = result
            return _tool_result(req_id, json.dumps(out, indent=2), is_error=not out['ok'])

        if tool_name == 'get_policy_brief':
            ensure_compiled()
            if not POLICY_BRIEF.exists():
                return _tool_error(req_id, 'No assistant-brief.md — compile training first')
            return _tool_result(req_id, read_text(POLICY_BRIEF))

        if tool_name == 'get_session_status':
            return _tool_result(req_id, json.dumps(build_session_status(), indent=2))

        if tool_name == 'get_agent_spine':
            return _tool_result(req_id, json.dumps(build_agent_spine(source='mcp'), indent=2))

        if tool_name == 'get_settings':
            return _tool_result(req_id, json.dumps(build_settings_api_payload(), indent=2))

        if tool_name == 'update_settings':
            args_obj = params.get('arguments', {})
            patch = args_obj.get('settings')
            if patch is None:
                patch = {k: v for k, v in args_obj.items() if k != 'compile'}
            if not isinstance(patch, dict):
                return _tool_error(req_id, 'settings patch must be a JSON object')
            compile_after = bool(args_obj.get('compile'))
            try:
                result = update_settings(patch, compile_after=compile_after)
            except ValueError as exc:
                return _tool_error(req_id, str(exc))
            if result.get('ok'):
                spine = build_agent_spine(source='mcp')
                result['spine'] = {
                    'activeSections': spine['activeSections'],
                    'dormantSections': spine['dormantSections'],
                }
            return _tool_result(req_id, json.dumps(result, indent=2), is_error=not result.get('ok'))

        if tool_name == 'list_mail_accounts':
            settings = load_settings()
            cfg = unified_inbox_config(settings)
            payload = {
                'enabled': cfg.get('enabled', False),
                'defaultAccountId': cfg.get('defaultAccountId'),
                'accounts': list_accounts(settings),
                'doc': 'references/unified-inbox.md',
            }
            return _tool_result(req_id, json.dumps(payload, indent=2))

        if tool_name == 'set_mail_accounts':
            from settings import save_settings

            args_obj = params.get('arguments', {})
            settings = load_settings()
            if 'enabled' in args_obj:
                cfg = unified_inbox_config(settings)
                cfg['enabled'] = bool(args_obj['enabled'])
                settings['unifiedInbox'] = cfg
            if args_obj.get('accounts') is not None:
                settings = merge_accounts(settings, args_obj['accounts'])
            save_settings(settings)
            spine = build_agent_spine(source='mcp')
            return _tool_result(req_id, json.dumps({
                'ok': True,
                'unifiedInbox': unified_inbox_config(settings),
                'spine': {
                    'activeSections': spine['activeSections'],
                    'dormantSections': spine['dormantSections'],
                },
            }, indent=2))

        if tool_name == 'get_policy_graph':
            ensure_compiled()
            if not POLICY_GRAPH.exists():
                return _tool_error(req_id, 'No policy-graph.json — compile training first')
            return _tool_result(req_id, json.dumps(load_json(POLICY_GRAPH), indent=2))

        if tool_name == 'get_calibration':
            ensure_compiled()
            if not CALIBRATION.exists():
                return _tool_error(req_id, 'No calibration.json — compile training first')
            return _tool_result(req_id, json.dumps(load_json(CALIBRATION), indent=2))

        pack = load_training_pack()
        if 'error' in pack:
            return _tool_error(req_id, pack['error'])

        if tool_name == 'get_training_pack':
            text = json.dumps(pack, indent=2)
        elif tool_name == 'get_watch_rules':
            text = json.dumps({
                'watchRules': pack.get('watchRules', []),
                'needsAttentionFolder': pack.get('needsAttentionFolder', {}),
                'runtimeGuidance': pack.get('runtimeGuidance', {}),
            }, indent=2)
        else:
            return {
                'jsonrpc': '2.0',
                'id': req_id,
                'error': {'code': -32601, 'message': f'Unknown tool: {tool_name}'},
            }

        return _tool_result(req_id, text)

    return {
        'jsonrpc': '2.0',
        'id': req_id,
        'error': {'code': -32601, 'message': f'Method not found: {method}'},
    }


def _tool_result(req_id, text: str, is_error: bool = False) -> dict:
    return {
        'jsonrpc': '2.0',
        'id': req_id,
        'result': {
            'content': [{'type': 'text', 'text': text}],
            'isError': is_error,
        },
    }


def _tool_error(req_id, message: str) -> dict:
    return _tool_result(req_id, message, is_error=True)


def run_stdio_server():
    print('Email Swipe MCP (training + policy brief) starting', file=sys.stderr)
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


def run_watch_mode(interval: float = 2.0):
    """Recompile when preferences.json changes (for agents not using serve-ui)."""
    print(f'Watching {PREFS_FILE} (poll every {interval}s)', file=sys.stderr)
    last_mtime = 0.0
    while True:
        if PREFS_FILE.exists():
            mtime = PREFS_FILE.stat().st_mtime
            if mtime > last_mtime:
                last_mtime = mtime
                result = compile_training(PREFS_FILE, USER_DIR, save_settings_from_prefs=True)
                status = 'ok' if result.get('ok') else result.get('error', 'failed')
                print(f'Compiled: {status}', file=sys.stderr)
        time.sleep(interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Email Swipe MCP server')
    parser.add_argument('--watch', action='store_true', help='Watch preferences.json and auto-compile')
    parser.add_argument('--interval', type=float, default=2.0, help='Watch poll interval (seconds)')
    args = parser.parse_args()
    if args.watch:
        run_watch_mode(args.interval)
    else:
        run_stdio_server()
