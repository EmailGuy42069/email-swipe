"""Canonical agent bootstrap context — one source of truth for skill activation."""

from __future__ import annotations

from agent_spine import SPINE_DOC, build_agent_spine, spine_summary_lines
from environment_state import ENVIRONMENT_FILE, environment_summary, load_environment
from settings import load_settings
from session_state import load_runtime


def build_agent_context() -> dict:
    """Return unambiguous activation guidance for agents."""
    runtime = load_runtime()
    settings = load_settings()
    env = load_environment()
    env_summary = environment_summary(env, settings)
    desktop_url = runtime.get('desktopUrl') if runtime else None

    return {
        'skill': 'email-swipe',
        'readFirst': ['AGENTS.md', 'references/agent-spine.md', 'SKILL.md'],
        'memoryModel': {
            'rule': (
                'Never memorize skill how-tos (UI open, activation order, tool routing). '
                'Re-hydrate every session via get_skill_context. '
                'Persist only machine-proven facts under ~/.config/email-swipe/environment.json '
                '(verified mail access after a successful fetch).'
            ),
            'skillIsMemory': [
                'How to open the UI',
                'Activation phases',
                'Tool routing and dormancy',
            ],
            'diskIsMemory': [
                'environment.json — per-account verified mail access (emailAccessByAccount)',
                'runtime.json — live Desktop/Mobile URL',
                'settings.json — UI mirror of agent spine + unifiedInbox registry',
            ],
            'hostMemoryPointerOnly': (
                'Cursor memories / CLAUDE.md / user AGENTS.md should only store a pointer '
                'to this skill path + “activate with get_skill_context”.'
            ),
        },
        'deployment': {
            'localFirst': True,
            'requiredCloud': False,
            'dataDir': '~/.config/email-swipe/',
            'persistence': (
                'Artifacts persist on the machine running serve-ui.py. '
                'Ephemeral remote hosts (containers, some PaaS) may lose data unless durable storage is configured.'
            ),
            'stackAgnostic': (
                'Any agent host with MCP (Cursor, OpenClaw, etc.) and any verified mail access '
                '(MCP, gog, IMAP, Graph, …). No Render or specific vendor required.'
            ),
            'runbook': 'references/deployment.md',
        },
        'access': {
            'exploreRemoteReachability': False,
            'doc': 'references/remote-access-power-user.md',
            'uiDoc': 'remote-access.html',
            'summary': (
                'User wants UI/settings reachable from anywhere (Tailscale, VPS, tunnel). '
                'Email Swipe does not host — read remote-access-power-user.md and help setup on same host as agent.'
            ),
        },
        'unifiedInbox': {
            'advancedSetting': True,
            'doc': 'references/unified-inbox.md',
            'uiDoc': 'unified-inbox.html',
            'summary': (
                'Optional multi-mailbox mode. Train one account per session; agent merges policies into one brief. '
                'Does not host mail. User registers accounts in chat with the agent — do not prompt for life context.'
            ),
            'agentUsesExternalContext': True,
            'doNotPrompt': ['calendar', 'life story', 'projects', 'relationships'],
        },
        'ui': {
            'singleEntryPoint': True,
            'file': 'assets/ui/index.html',
            'open': 'Run `python scripts/serve-ui.py` and open the Desktop URL printed at startup',
            'port': 'Dynamic — do not assume 8765; read runtime.json or server output',
            'desktopUrl': desktop_url,
            'runtimeFile': '~/.config/email-swipe/runtime.json',
            'doNotUse': ['demo.html', 'demo-app.js'],
            'demoMeans': (
                'Sample mail from demo-emails.json (via session-intake.py demo or automatic fallback), '
                'not a separate HTML page'
            ),
        },
        'environment': {
            'file': str(ENVIRONMENT_FILE),
            'doc': 'references/email-access-gate.md',
            'summary': env_summary,
            'current': env,
            'recordTool': 'record_email_access',
            'whenToRecord': (
                'After a successful 5–10 message fetch per account, call record_email_access '
                'with accountId (unified inbox) or omit accountId for single inbox. '
                'Next activation merges registry (spine) + verified fetch (environment).'
            ),
        },
        'gitStatus': {
            'ignoreThese': [
                'assets/ui/emails.json',
                'assets/ui/settings.json',
                'assets/ui/session-metadata.json',
            ],
            'note': (
                'Gitignored runtime files appear after sessions. '
                'Do not treat dirty git status as alternate skill versions or a reason to switch UIs.'
            ),
        },
        'activation': {
            'orderedPhases': [
                'get_skill_context (or read AGENTS.md)',
                'session_intake_assess',
                'email access gate — check_email_access + ask user (references/email-access-gate.md)',
                'discovery conversation → session_intake_discover',
                'session_intake_recommend — present all four paths',
                'user chooses → session_intake_confirm',
                'execute path runbook (references/paths/)',
                'post-training: get_session_status + get_policy_brief',
            ],
            'evaluatorDemo': [
                'python scripts/session-intake.py demo',
                'python scripts/serve-ui.py',
                'Open printed Desktop URL — same index.html UI',
            ],
            'realSession': [
                'session_intake_assess (or session-intake.py assess)',
                'check_email_access + email discovery questions',
                'Discovery conversation → discover → recommend',
                'User picks path → confirm',
                'Execute path runbook (references/paths/)',
            ],
            'doNotBeforeConfirm': ['inject-emails.py', 'serve-ui.py'],
            'doNotSkip': [
                'Discovery conversation before recommend',
                'User path choice before confirm',
                'Email access gate before real-mail inject',
                'Post-training brief presentation',
            ],
            'exceptImportSorting': 'import-sorting path skips the swipe UI entirely',
        },
        'emailAccess': {
            'uiNeverFetchesMail': True,
            'checkTool': 'check_email_access',
            'recordTool': 'record_email_access',
            'checkCli': 'python scripts/detect-environment.py',
            'runbook': 'references/email-access-gate.md',
            'persistedFile': '~/.config/email-swipe/environment.json',
            'skipRediscoveryWhen': (
                'Single inbox: any verified record. Unified inbox: all registered accounts verified.'
            ),
            'askFirst': [
                'Do I already have access to your email (MCP, gog, IMAP, Graph)?',
                'Which provider?',
                'Real inbox or demo first?',
            ],
            'realMailRequires': 'Verified fetch of 5–10 messages before inject-emails.py',
            'demoFallback': 'session-intake.py demo or demo-emails.json UI fallback',
            'current': env_summary,
        },
        'afterTraining': [
            'get_agent_spine',
            'get_session_status',
            'get_policy_brief',
            'Present assistant-brief.md to user (references/post-training-flow.md)',
        ],
        'spine': {
            'doc': SPINE_DOC,
            'sourceOfTruth': 'agent',
            'diskMirror': '~/.config/email-swipe/settings.json',
            'summary': (
                'You own advanced settings in memory (the spine). Disk and UI mirror the spine. '
                'Most sections are dormant. Before opening the UI: update_settings. '
                'After UI feedback: get_agent_spine. Before mail actions: read activeSections only.'
            ),
            'hydrate': 'get_agent_spine',
            'pushToUi': 'update_settings',
            'loops': {
                'beforeOpenUi': [
                    'Merge chat into spine',
                    'update_settings with spine.settings',
                    'serve-ui.py → Desktop URL',
                ],
                'afterUiFeedback': [
                    'get_agent_spine',
                    'Merge into agent memory',
                    'Do not re-ask dormant fields',
                ],
                'beforeMailAction': [
                    'Check spine.activeSections',
                    'Use policy-graph + assistant-brief for trained rules',
                ],
            },
            'toolRouting': {
                'read': 'get_agent_spine (preferred) or get_settings',
                'write': 'update_settings',
                'inboxesRegistry': 'set_mail_accounts — then merge into spine',
                'avoid': ['list_mail_accounts alone', 'assets/ui/settings.json', 'localStorage'],
            },
            'dormantByDefault': [
                'unifiedInbox',
                'sorting.advanced',
                'rules.autonomy',
                'rhythm',
                'access.remote',
                'context',
            ],
            'current': build_agent_spine(source='activation'),
        },
        'docs': {
            'agents': 'AGENTS.md',
            'skill': 'SKILL.md',
            'agentSpine': SPINE_DOC,
            'quickstart': 'references/QUICKSTART.md',
            'intake': 'references/intake-router.md',
            'emailAccess': 'references/email-access-gate.md',
            'postTraining': 'references/post-training-flow.md',
            'advancedSettings': 'docs/ADVANCED-SETTINGS-SPEC.md',
            'unifiedInbox': 'references/unified-inbox.md',
            'remoteAccess': 'references/remote-access-power-user.md',
        },
    }


def activation_summary_lines() -> list[str]:
    """Short lines for CLI banners."""
    ctx = build_agent_context()
    env = ctx['environment']['summary']
    lines = [
        'Agent: one UI only — index.html at the Desktop URL printed below.',
        'Demo = sample mail, not demo.html. Ignore gitignored runtime files in git status.',
        'Real sessions: assess → email gate → discover → recommend → confirm.',
        'Never memorize skill how-tos — rehydrate get_skill_context; persist verified mail per account in environment.json.',
        f"Docs: {ctx['docs']['agents']}, {ctx['docs']['agentSpine']}",
    ]
    if env.get('unifiedInbox') and env.get('registeredAccountCount'):
        lines.append(
            f"Unified inbox: {env.get('verifiedAccountCount', 0)}/{env['registeredAccountCount']} "
            'accounts verified on disk.'
        )
    elif env.get('verified'):
        verified_accounts = [a for a in env.get('accounts') or [] if a.get('verified')]
        if verified_accounts:
            rec = verified_accounts[0]
            lines.append(
                f"Verified mail: {rec.get('method')} ({rec.get('label') or rec.get('accountId')}) "
                '— skip rediscovery unless fetch fails.'
            )
    else:
        lines.append('No verified mail access on disk yet — check_email_access then record_email_access per account.')
    lines.extend(spine_summary_lines(ctx['spine']['current']))
    return lines
