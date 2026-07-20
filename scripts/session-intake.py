#!/usr/bin/env python3
"""Session intake — discover context, recommend a path, confirm before training."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_context import build_agent_context
from email_access_gate import build_email_access_status
from settings import USER_DIR, load_settings
from accounts import list_accounts, unified_inbox_config

INTAKE_FILE = USER_DIR / 'intake.json'
POLICY_GRAPH = USER_DIR / 'policy-graph.json'
CALIBRATION = USER_DIR / 'calibration.json'
PREFS_FILE = USER_DIR / 'preferences.json'
TRAINING_PACK = USER_DIR / 'training-pack.json'

PATHS = ('bootstrap', 'calibrate', 'refine', 'import-sorting')
PHASES = ('assess', 'discovery', 'recommended', 'confirmed', 'in_progress', 'completed')

PATH_LABELS = {
    'bootstrap': 'Bootstrap — swipe a broad inbox sample to learn your patterns from scratch',
    'calibrate': 'Calibrate — import existing rules, then swipe only emails I am uncertain about',
    'refine': 'Refine — short follow-up session on specific gaps from prior training',
    'import-sorting': 'Import sorting — no swiping; learn rules from how your folders are already organized',
}

# Paths that skip the swipe UI entirely (backend-only).
NO_UI_PATHS = ('import-sorting',)

IMPORT_SORTING_CAUTION = (
    'Backend-only path — no swipe UI. Before applying, confirm with the user: '
    '(1) their sorting still reflects current preferences, (2) folders may hold '
    'stale or lingering mail that would teach the wrong rule. Run '
    'learn_from_folders.py --preview first and review the plan together.'
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_intake() -> dict:
    if INTAKE_FILE.exists():
        with open(INTAKE_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    return {
        'version': '1.0',
        'phase': 'assess',
        'createdAt': _now(),
        'updatedAt': _now(),
        'signals': {},
        'discovery': {},
        'recommendedPath': None,
        'recommendationReason': None,
        'selectedPath': None,
        'confirmedAt': None,
    }


def save_intake(data: dict) -> Path:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    data['updatedAt'] = _now()
    with open(INTAKE_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    return INTAKE_FILE


def detect_signals() -> dict:
    """Inspect local artifacts and infer what we already know."""
    signals = {
        'hasPolicyGraph': POLICY_GRAPH.exists(),
        'hasCalibration': CALIBRATION.exists(),
        'hasPreferences': PREFS_FILE.exists(),
        'hasTrainingPack': TRAINING_PACK.exists(),
        'importedRuleCount': 0,
        'confirmedRuleCount': 0,
        'trainingGapCount': 0,
        'policyCandidateCount': 0,
        'priorSwipeCount': 0,
        'overallAgreement': None,
        'inconsistentSenderCount': 0,
    }

    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE) as f:
                prefs = json.load(f)
            signals['priorSwipeCount'] = len(prefs.get('swipes', []))
        except (json.JSONDecodeError, OSError):
            pass

    if POLICY_GRAPH.exists():
        try:
            with open(POLICY_GRAPH) as f:
                graph = json.load(f)
            policies = graph.get('policies', [])
            signals['importedRuleCount'] = sum(
                1 for p in policies if p.get('source') == 'imported' or p.get('userConfirmed')
            )
            signals['confirmedRuleCount'] = sum(1 for p in policies if p.get('userConfirmed'))
            signals['trainingGapCount'] = len(graph.get('trainingGaps', []))
            signals['policyCandidateCount'] = len(graph.get('policyCandidates', []))
        except (json.JSONDecodeError, OSError):
            pass

    if CALIBRATION.exists():
        try:
            with open(CALIBRATION) as f:
                cal = json.load(f)
            signals['overallAgreement'] = cal.get('overall', {}).get('agreement')
            signals['inconsistentSenderCount'] = len(cal.get('inconsistentSenders', []))
        except (json.JSONDecodeError, OSError):
            pass

    return signals


def recommend_path(signals: dict, discovery: dict) -> tuple[str, str]:
    """Return (path, reason) from signals + discovery answers."""
    has_rules = discovery.get('hasExistingRules')
    rules_source = discovery.get('rulesSource', '')
    goal = discovery.get('goal', '')
    prior_sessions = discovery.get('priorSwipeSessions')
    wants_demo = discovery.get('demoFirst', False)

    # No-UI path: user already sorts mail into folders and wants rules learned
    # from that, not from swiping. Only recommend when they lean away from the UI.
    if (discovery.get('learnFromSorting') or goal == 'learn_from_sorting') and discovery.get('preferUi') is not True:
        return 'import-sorting', (
            'Your folders are already organized and you would rather not swipe — '
            'I can learn routing rules directly from how mail is filed. We will '
            'preview the rules first, since folders can hold stale mail or outdated choices.'
        )

    if wants_demo and not signals.get('hasPreferences'):
        return 'bootstrap', (
            'You asked for a demo first with no prior swipe data — a short bootstrap session '
            'is the fastest way to see how training works.'
        )

    if goal == 'close_specific_gaps' or signals.get('trainingGapCount', 0) > 0:
        if signals.get('hasPolicyGraph') or signals.get('hasPreferences'):
            return 'refine', (
                'You already have training artifacts and specific gaps to close — '
                'a targeted refine session beats re-swiping your whole inbox.'
            )

    if has_rules or rules_source in ('agent_memory', 'platform_filters', 'policy_graph', 'verbal'):
        if goal in ('import_rules', 'fix_uncertain_areas', '') or signals.get('importedRuleCount', 0) > 0:
            return 'calibrate', (
                'You already have email rules — import them, then swipe only edge cases '
                'where confidence is low instead of training from scratch.'
            )

    if signals.get('hasPolicyGraph') and signals.get('priorSwipeCount', 0) > 0:
        if signals.get('overallAgreement') is not None and signals['overallAgreement'] < 0.75:
            return 'refine', (
                'Prior training exists but agreement was below 75% — '
                'a refine pass on weak areas will help more than starting over.'
            )
        if signals.get('trainingGapCount', 0) > 0 or signals.get('inconsistentSenderCount', 0) > 0:
            return 'refine', (
                'Calibration flagged inconsistent senders or training gaps — '
                'refine on those senders next.'
            )

    if prior_sessions is False and not signals.get('hasPreferences'):
        return 'bootstrap', (
            'No prior swipe sessions or policy graph found — '
            'bootstrap training will establish your baseline preferences.'
        )

    if signals.get('hasPreferences') and not has_rules:
        return 'bootstrap', (
            'You have swipe history but no formal rules yet — '
            'another bootstrap round or reviewing the brief may help; bootstrap is the default.'
        )

    return 'bootstrap', (
        'Default path when context is unclear — swipe a representative inbox sample, '
        'then review the brief together.'
    )


def discovery_questions(signals: dict) -> list[dict]:
    """Questions the agent should ask before recommending a path."""
    questions = []

    if signals.get('hasPolicyGraph') or signals.get('hasPreferences'):
        questions.append({
            'id': 'resume_or_restart',
            'prompt': 'You have prior Email Swipe training on this machine. Continue from that, or start fresh?',
            'why': 'Detects refine vs bootstrap without assuming.',
        })
    else:
        questions.append({
            'id': 'first_time',
            'prompt': 'Is this your first time training email preferences with me, or do you already sort mail with rules elsewhere?',
            'why': 'Separates bootstrap from calibrate.',
        })

    questions.extend([
        {
            'id': 'agent_has_mail_access',
            'prompt': (
                'Do I already have access to your email from another tool '
                '(Gmail MCP, gog CLI, IMAP, Microsoft Graph, or similar)?'
            ),
            'why': 'Local auto-detect may miss MCP-only access — always ask.',
        },
        {
            'id': 'email_provider',
            'prompt': 'Which email provider is this? (Gmail, Outlook, Fastmail, iCloud, Exchange, other)',
            'why': 'Chooses setup path when access is missing.',
        },
        {
            'id': 'has_existing_rules',
            'prompt': 'Do you already have email rules — filters, labels, or habits you use with an agent — that we should import?',
            'why': 'Routes rules-first users to calibrate.',
        },
        {
            'id': 'folders_already_sorted',
            'prompt': (
                'Is your inbox already sorted into folders the way you like it? If so, I can learn '
                'rules straight from that instead of having you swipe — but only if that sorting '
                'still reflects what you want (folders sometimes hold stale mail).'
            ),
            'why': 'Offers the no-UI import-sorting path; confirms sorting is still trustworthy.',
        },
        {
            'id': 'inbox_goal',
            'prompt': 'What is the main problem you want help with? (e.g. promo noise, missing important mail, vendor pitches)',
            'why': 'Shapes queue selection and brief conversation.',
        },
        {
            'id': 'demo_or_real',
            'prompt': 'Want to start with demo emails to learn the UI, or load your real inbox into the swipe trainer?',
            'why': 'Demo still uses bootstrap but sets expectations.',
        },
        {
            'id': 'deployment',
            'prompt': 'How do you want to run the swipe UI — desktop browser, phone on the same Wi‑Fi, or something else?',
            'why': 'Needed before serve-ui; not path-specific.',
        },
    ])

    if signals.get('trainingGapCount', 0) > 0:
        questions.append({
            'id': 'gap_focus',
            'prompt': (
                f'Last training flagged {signals["trainingGapCount"]} area(s) I am still uncertain about. '
                'Want a short refine session on those?'
            ),
            'why': 'Offers refine when artifacts show gaps.',
        })

    return questions


def merge_discovery(intake: dict, answers: dict) -> dict:
    """Normalize discovery answers from agent chat into intake.discovery."""
    d = intake.setdefault('discovery', {})

    if 'hasExistingRules' in answers:
        d['hasExistingRules'] = bool(answers['hasExistingRules'])
    if 'rulesSource' in answers:
        d['rulesSource'] = answers['rulesSource']
    if 'priorSwipeSessions' in answers:
        d['priorSwipeSessions'] = bool(answers['priorSwipeSessions'])
    if 'goal' in answers:
        d['goal'] = answers['goal']
    if 'demoFirst' in answers:
        d['demoFirst'] = bool(answers['demoFirst'])
    if 'learnFromSorting' in answers:
        d['learnFromSorting'] = bool(answers['learnFromSorting'])
    if 'preferUi' in answers:
        d['preferUi'] = bool(answers['preferUi'])
    if 'inboxType' in answers:
        d['inboxType'] = answers['inboxType']
    if 'problemToSolve' in answers:
        d['problemToSolve'] = answers['problemToSolve']
    if 'deployment' in answers:
        d['deployment'] = answers['deployment']
    if 'emailProvider' in answers:
        d['emailProvider'] = answers['emailProvider']
    if 'agentHasMailAccess' in answers:
        d['agentHasMailAccess'] = bool(answers['agentHasMailAccess'])
    if 'wantsRealMail' in answers:
        d['wantsRealMail'] = bool(answers['wantsRealMail'])
    if 'notes' in answers:
        d['notes'] = answers['notes']

    # Infer from common answer shapes
    if answers.get('has_existing_rules') is True:
        d['hasExistingRules'] = True
        d.setdefault('rulesSource', 'verbal')
    if answers.get('first_time') is False:
        d['priorSwipeSessions'] = True
    if answers.get('demo_or_real') == 'demo':
        d['demoFirst'] = True
        d['wantsRealMail'] = False
    if answers.get('demo_or_real') == 'real':
        d['demoFirst'] = False
        d['wantsRealMail'] = True
    if answers.get('agent_has_mail_access') is True:
        d['agentHasMailAccess'] = True
    if answers.get('agent_has_mail_access') is False:
        d['agentHasMailAccess'] = False
    if answers.get('email_provider'):
        d['emailProvider'] = answers['email_provider']
    if answers.get('folders_already_sorted') is True:
        d['learnFromSorting'] = True

    return d


def build_recommendation(intake: dict) -> dict:
    signals = intake.get('signals') or detect_signals()
    intake['signals'] = signals
    path, reason = recommend_path(signals, intake.get('discovery', {}))
    intake['recommendedPath'] = path
    intake['recommendationReason'] = reason
    intake['phase'] = 'recommended'
    intake['pathOptions'] = [
        {'id': p, 'label': PATH_LABELS[p], 'recommended': p == path}
        for p in PATHS
    ]
    return intake


def cmd_assess(_args: argparse.Namespace) -> int:
    intake = load_intake()
    intake['signals'] = detect_signals()
    intake['phase'] = 'assess'
    email_access = build_email_access_status()
    intake['emailAccess'] = email_access
    intake['questions'] = discovery_questions(intake['signals'])
    intake['emailAccessQuestions'] = email_access['agentQuestions']
    save_intake(intake)
    ctx = build_agent_context()
    settings = load_settings()
    ui_cfg = unified_inbox_config(settings)
    print(json.dumps({
        'phase': intake['phase'],
        'agentContext': ctx,
        'emailAccess': email_access,
        'unifiedInbox': {
            'enabled': ui_cfg.get('enabled', False),
            'accounts': list_accounts(settings),
            'doc': 'references/unified-inbox.md',
            'note': (
                'When enabled, train one mailbox per session with metadata.accountId. '
                'Register accounts in chat — do not add life-context prompts.'
            ) if ui_cfg.get('enabled') else (
                'Optional advanced setting in Advanced settings. Off by default for single inbox.'
            ),
        },
        'access': {
            'exploreRemoteReachability': bool((settings.get('access') or {}).get('exploreRemoteReachability')),
            'doc': 'references/remote-access-power-user.md',
            'agentAction': (
                'User enabled Explore remote access — read remote-access-power-user.md and help them '
                'run serve-ui.py on an always-on host with agent + MCP (Tailscale or VPS recommended).'
            ) if (settings.get('access') or {}).get('exploreRemoteReachability') else None,
        },
        'signals': intake['signals'],
        'questions': intake['questions'],
        'emailAccessQuestions': intake['emailAccessQuestions'],
        'message': (
            'Read agentContext first. Resolve email access (emailAccess + emailAccessQuestions) '
            'during discovery. Do not inject emails or start serve-ui until path is confirmed.'
        ),
    }, indent=2))
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    intake = load_intake()
    answers = json.loads(args.answers) if args.answers else {}
    merge_discovery(intake, answers)
    intake['signals'] = detect_signals()
    intake['phase'] = 'discovery'
    save_intake(intake)
    print(json.dumps({'ok': True, 'phase': intake['phase'], 'discovery': intake['discovery']}, indent=2))
    return 0


def cmd_recommend(_args: argparse.Namespace) -> int:
    intake = load_intake()
    intake = build_recommendation(intake)
    discovery = intake.get('discovery', {})
    email_access = intake.get('emailAccess') or build_email_access_status()
    intake['emailAccess'] = email_access
    save_intake(intake)

    wants_real = discovery.get('wantsRealMail')
    if wants_real is None and not discovery.get('demoFirst'):
        wants_real = True  # default assumption unless demo chosen
    mail_warnings = []
    if wants_real and not email_access.get('hasAccess') and not discovery.get('agentHasMailAccess'):
        mail_warnings.append(
            'BLOCKER: User wants real mail but no mail connector detected. '
            'Guide setup per references/email-access-gate.md or offer demo — do not inject yet.'
        )
    elif wants_real and discovery.get('agentHasMailAccess') and not email_access.get('hasAccess'):
        mail_warnings.append(
            'User reports mail access via agent MCP/tool — verify a 5–10 message fetch before inject.'
        )

    print(json.dumps({
        'phase': intake['phase'],
        'recommendedPath': intake['recommendedPath'],
        'recommendationReason': intake['recommendationReason'],
        'pathOptions': intake['pathOptions'],
        'emailAccess': email_access,
        'mailWarnings': mail_warnings,
        'agentPrompt': (
            f"I recommend **{intake['recommendedPath']}**: {intake['recommendationReason']}\n\n"
            "Which path do you want?\n"
            + '\n'.join(
                f"- **{o['id']}**{' (recommended)' if o['recommended'] else ''}: {o['label']}"
                for o in intake['pathOptions']
            )
            + "\n\nSay the path name, or tell me what you prefer and we can adjust."
        ),
    }, indent=2))
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    intake = load_intake()
    path = args.path
    if path not in PATHS:
        print(json.dumps({'ok': False, 'error': f'path must be one of {PATHS}'}), file=sys.stderr)
        return 1
    intake['selectedPath'] = path
    intake['confirmedAt'] = _now()
    intake['phase'] = 'confirmed'
    if not intake.get('recommendedPath'):
        intake = build_recommendation(intake)
        intake['selectedPath'] = path
        intake['confirmedAt'] = _now()
        intake['phase'] = 'confirmed'
    save_intake(intake)
    response = {
        'ok': True,
        'selectedPath': path,
        'sessionMode': path,
        'usesSwipeUi': path not in NO_UI_PATHS,
        'next': f'See references/intake-router.md → path "{path}" for steps.',
    }
    if path == 'import-sorting':
        response['caution'] = IMPORT_SORTING_CAUTION
        response['nextTool'] = (
            'Fetch folder contents, then run learn_from_folders.py --preview and '
            'review the plan with the user BEFORE applying (no --preview).'
        )
        response['runbook'] = 'references/paths/import-sorting.md'
    print(json.dumps(response, indent=2))
    return 0


def cmd_get(_args: argparse.Namespace) -> int:
    intake = load_intake()
    if not intake.get('signals'):
        intake['signals'] = detect_signals()
    print(json.dumps(intake, indent=2))
    return 0


def cmd_demo(_args: argparse.Namespace) -> int:
    """Evaluator shortcut: confirm bootstrap + inject demo mail (skip full intake)."""
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent
    demo_file = repo_root / 'assets' / 'ui' / 'demo-emails.json'
    inject_script = repo_root / 'scripts' / 'inject-emails.py'

    if not demo_file.exists():
        print(json.dumps({'ok': False, 'error': f'demo file missing: {demo_file}'}), file=sys.stderr)
        return 1

    with open(demo_file) as f:
        emails = json.load(f)

    intake = load_intake()
    intake['signals'] = detect_signals()
    intake['discovery'] = {'demoFirst': True, 'goal': 'demo', 'preferUi': True}
    intake['recommendedPath'] = 'bootstrap'
    intake['selectedPath'] = 'bootstrap'
    intake['confirmedAt'] = _now()
    intake['phase'] = 'confirmed'
    save_intake(intake)

    batch = {
        'metadata': {
            'sessionMode': 'bootstrap',
            'intakePath': 'bootstrap',
            'demo': True,
            'generatedAt': _now(),
        },
        'emails': emails,
    }
    batch_path = USER_DIR / 'demo-batch.json'
    USER_DIR.mkdir(parents=True, exist_ok=True)
    with open(batch_path, 'w') as f:
        json.dump(batch, f, indent=2)
        f.write('\n')

    result = subprocess.run(
        [sys.executable, str(inject_script), str(batch_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(json.dumps({
            'ok': False,
            'error': 'inject-emails failed',
            'stderr': result.stderr,
        }), file=sys.stderr)
        return 1

    print(json.dumps({
        'ok': True,
        'mode': 'demo',
        'selectedPath': 'bootstrap',
        'emailsInjected': len(emails),
        'batchPath': str(batch_path),
        'agentContext': build_agent_context(),
        'message': (
            'Demo ready — evaluator shortcut (full intake skipped). '
            'Run serve-ui.py and open the Desktop URL it prints (index.html — the only UI).'
        ),
        'nextSteps': [
            'python scripts/serve-ui.py',
            'Open the printed Desktop URL and swipe demo mail (same index.html UI)',
            'After session: get_session_status + get_policy_brief (MCP)',
            'See references/post-training-flow.md for cementing conversation',
        ],
        'note': 'For real training, run full intake (assess → discover → recommend → confirm).',
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Email Swipe session intake')
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('assess', help='Detect local signals + return discovery questions')

    p_disc = sub.add_parser('discover', help='Save discovery answers from chat')
    p_disc.add_argument('answers', nargs='?', help='JSON object of discovery answers')

    sub.add_parser('recommend', help='Recommend a path after discovery')

    p_conf = sub.add_parser('confirm', help='Lock selected path before training')
    p_conf.add_argument('path', choices=PATHS)

    sub.add_parser('get', help='Print current intake state')

    sub.add_parser(
        'demo',
        help='Evaluator shortcut: confirm bootstrap + inject demo emails (skip full intake)',
    )

    args = parser.parse_args()
    handlers = {
        'assess': cmd_assess,
        'discover': cmd_discover,
        'recommend': cmd_recommend,
        'confirm': cmd_confirm,
        'get': cmd_get,
        'demo': cmd_demo,
    }
    return handlers[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
