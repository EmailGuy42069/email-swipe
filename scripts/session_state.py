#!/usr/bin/env python3
"""Runtime/session status helpers for Email Swipe."""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from settings import USER_DIR

RUNTIME_FILE = USER_DIR / 'runtime.json'
SESSION_COMPLETE_FILE = USER_DIR / 'session-complete.json'
SESSION_HISTORY_FILE = USER_DIR / 'session-history.json'
SESSION_PROGRESS_FILE = USER_DIR / 'session-progress.json'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
    return f'{stamp}-{secrets.token_hex(2)}'


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    return path


def load_runtime() -> dict:
    return _read_json(RUNTIME_FILE)


def write_runtime(
    session_id: str,
    port: int,
    desktop_url: str,
    lan_url: str | None = None,
    *,
    status: str = 'in_progress',
    server_pid: int | None = None,
) -> dict:
    data = {
        'sessionId': session_id,
        'port': port,
        'desktopUrl': desktop_url,
        'lanUrl': lan_url,
        'startedAt': now_iso(),
        'serverPid': server_pid or os.getpid(),
        'status': status,
    }
    _write_json(RUNTIME_FILE, data)
    return data


def update_runtime_status(status: str, **extra) -> dict:
    runtime = load_runtime()
    if not runtime:
        return {}
    runtime['status'] = status
    runtime.update(extra)
    _write_json(RUNTIME_FILE, runtime)
    return runtime


def load_session_completion() -> dict:
    return _read_json(SESSION_COMPLETE_FILE)


def write_session_completion(data: dict) -> dict:
    _write_json(SESSION_COMPLETE_FILE, data)
    return data


def load_session_history() -> dict:
    history = _read_json(SESSION_HISTORY_FILE)
    if not history:
        return {'version': '1.0', 'updatedAt': None, 'sessions': []}
    history.setdefault('version', '1.0')
    history.setdefault('updatedAt', None)
    history.setdefault('sessions', [])
    return history


def summarize_completion(completion: dict) -> dict:
    score = completion.get('scoreSummary', {})
    return {
        'sessionId': completion.get('sessionId'),
        'completedAt': completion.get('completedAt'),
        'sessionMode': completion.get('sessionMode'),
        'intakePath': completion.get('intakePath'),
        'accountId': completion.get('accountId'),
        'accountLabel': completion.get('accountLabel'),
        'swipeCount': completion.get('swipeCount', 0),
        'scorablePredictions': score.get('scorablePredictions', 0),
        'correctPredictions': score.get('correctPredictions', 0),
        'agreement': score.get('agreement'),
        'reversedInReview': score.get('reversedInReview', 0),
        'correctionCount': score.get('correctionCount', 0),
        'trainingGapCount': score.get('trainingGapCount', 0),
    }


def compute_score_trend(sessions: list[dict]) -> dict:
    scored = [s for s in sessions if isinstance(s.get('agreement'), (int, float))]
    if len(scored) < 2:
        latest = scored[-1] if scored else {}
        return {
            'status': 'insufficient_data',
            'tone': 'neutral',
            'latestAgreement': latest.get('agreement'),
            'previousAgreement': None,
            'delta': None,
            'needsAttention': False,
            'message': 'Not enough scored sessions yet to judge improvement.',
            'headline': 'Still learning',
        }

    latest = scored[-1]
    previous = scored[-2]
    delta = round(float(latest['agreement']) - float(previous['agreement']), 4)
    status = 'flat'
    if delta >= 0.04:
        status = 'improved'
    elif delta <= -0.04:
        status = 'declined'

    needs_attention = False
    tone = 'neutral'
    if status == 'declined':
        needs_attention = True
        tone = 'warning'
    elif status == 'flat' and float(latest['agreement']) < 0.70 and len(scored) >= 2:
        if float(previous['agreement']) < 0.70:
            needs_attention = True
            tone = 'warning'
    if latest.get('trainingGapCount', 0) > previous.get('trainingGapCount', 0):
        needs_attention = True
        tone = 'warning'
    if status == 'improved':
        tone = 'positive'

    headline = {
        'improved': 'Improved',
        'flat': 'No clear change',
        'declined': 'Needs attention',
    }[status]
    message = {
        'improved': 'Your agent is getting better at matching your choices.',
        'flat': 'No meaningful movement yet — another focused session may help.',
        'declined': 'The latest session slipped, so one or more learned rules likely need review.',
    }[status]
    if status == 'flat' and float(latest['agreement']) >= 0.80:
        message = 'Performance stayed strong — no major shift, but the agent is holding up well.'
        tone = 'positive'
        headline = 'Holding steady'
    elif status == 'flat' and needs_attention:
        headline = 'Needs attention'
        message = 'Performance stayed flat at a weak level — a targeted follow-up session is recommended.'

    return {
        'status': status,
        'tone': tone,
        'latestAgreement': latest.get('agreement'),
        'previousAgreement': previous.get('agreement'),
        'delta': delta,
        'needsAttention': needs_attention,
        'message': message,
        'headline': headline,
    }


def append_session_history(completion: dict) -> dict:
    history = load_session_history()
    sessions = [s for s in history.get('sessions', []) if s.get('sessionId') != completion.get('sessionId')]
    sessions.append(summarize_completion(completion))
    sessions = sorted(sessions, key=lambda x: x.get('completedAt') or '')
    history['sessions'] = sessions
    history['updatedAt'] = now_iso()
    _write_json(SESSION_HISTORY_FILE, history)
    return history


def empty_session_progress() -> dict:
    return {
        'version': '1.0',
        'inboxFingerprint': None,
        'swipes': [],
        'correctionNotes': {},
        'completed': False,
        'updatedAt': None,
    }


def load_session_progress() -> dict:
    data = _read_json(SESSION_PROGRESS_FILE)
    if not data:
        return empty_session_progress()
    base = empty_session_progress()
    base.update({k: v for k, v in data.items() if k in base or k in ('version',)})
    if not isinstance(base.get('swipes'), list):
        base['swipes'] = []
    if not isinstance(base.get('correctionNotes'), dict):
        base['correctionNotes'] = {}
    return base


def save_session_progress(payload: dict) -> dict:
    """Persist in-progress swipes so the UI can resume after leaving the tab."""
    current = load_session_progress()
    progress = empty_session_progress()
    progress['inboxFingerprint'] = payload.get('inboxFingerprint') or current.get('inboxFingerprint')
    swipes = payload.get('swipes')
    progress['swipes'] = swipes if isinstance(swipes, list) else current.get('swipes') or []
    notes = payload.get('correctionNotes')
    progress['correctionNotes'] = notes if isinstance(notes, dict) else current.get('correctionNotes') or {}
    if 'completed' in payload:
        progress['completed'] = bool(payload.get('completed'))
    else:
        progress['completed'] = bool(current.get('completed'))
    progress['updatedAt'] = now_iso()
    _write_json(SESSION_PROGRESS_FILE, progress)
    return progress


def clear_session_progress() -> dict:
    progress = empty_session_progress()
    progress['updatedAt'] = now_iso()
    _write_json(SESSION_PROGRESS_FILE, progress)
    return progress


def build_session_status() -> dict:
    runtime = load_runtime()
    completion = load_session_completion()
    history = load_session_history()
    status = 'idle'
    if runtime:
        status = runtime.get('status', 'in_progress')
    elif completion:
        status = 'completed'
    trend = compute_score_trend(history.get('sessions', []))
    return {
        'status': status,
        'activeSessionId': runtime.get('sessionId') if runtime else None,
        'lastCompletedSessionId': completion.get('sessionId') if completion else None,
        'runtime': runtime or None,
        'lastCompletion': completion or None,
        'scoreTrend': trend,
        'recentHistory': history.get('sessions', [])[-6:],
    }
