#!/usr/bin/env python3
"""Shared compile entrypoint for serve-ui, MCP, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

from script_imports import analyze_preferences_mod as _ap
from policy_compiler import (
    build_assistant_brief,
    build_calibration,
    build_policy_graph,
    write_policy_artifacts,
)
from session_state import (
    append_session_history,
    build_session_status,
    compute_score_trend,
    load_runtime,
    now_iso,
    update_runtime_status,
    write_session_completion,
)
from settings import SETTINGS_FILE, USER_DIR, _deep_merge, load_settings, save_settings

analyze_preferences = _ap.analyze_preferences
build_training_pack = _ap.build_training_pack
write_outputs = _ap.write_outputs


def compile_training(
    prefs_path: Path | None = None,
    output_dir: Path | None = None,
    save_settings_from_prefs: bool = False,
    session_id: str | None = None,
) -> dict:
    """Compile all training artifacts from preferences.json. Returns paths + summary."""
    prefs_path = prefs_path or USER_DIR / 'preferences.json'
    output_dir = output_dir or USER_DIR

    if not prefs_path.exists():
        return {'ok': False, 'error': f'preferences not found: {prefs_path}'}

    with open(prefs_path) as f:
        preferences = json.load(f)

    settings = load_settings(SETTINGS_FILE if SETTINGS_FILE.exists() else None)
    if preferences.get('settings'):
        settings = _deep_merge(settings, preferences['settings'])
        if save_settings_from_prefs:
            save_settings(settings)

    swipes = preferences.get('swipes', [])
    outputs = analyze_preferences(preferences, settings)

    policy_graph = build_policy_graph(
        preferences,
        outputs['platformRules'],
        outputs['agentWatchlist'],
        swipes,
        settings,
    )
    calibration = build_calibration(preferences, swipes)
    brief = build_assistant_brief(
        preferences,
        policy_graph,
        calibration,
        outputs['agentWatchlist'],
        settings,
    )
    artifact_paths = write_policy_artifacts(output_dir, policy_graph, calibration, brief)

    outputs['trainingPack'] = build_training_pack(
        preferences,
        settings,
        outputs['folderSuggestions'],
        outputs['platformRules'],
        outputs['agentWatchlist'],
        outputs['analysisSummary'],
        artifact_refs=artifact_paths,
    )
    write_outputs(outputs, output_dir)

    summary = outputs['analysisSummary']
    headline = summary.get('headline', '')
    brief_first_line = brief.split('\n', 1)[0].strip('# ').strip()

    runtime = load_runtime()
    session_id = (
        session_id
        or preferences.get('metadata', {}).get('sessionId')
        or runtime.get('sessionId')
        or f'compile-{now_iso()}'
    )
    score_summary = {
        'agreement': calibration.get('overall', {}).get('agreement'),
        'scorablePredictions': calibration.get('overall', {}).get('scorable', 0),
        'correctPredictions': calibration.get('overall', {}).get('correct', 0),
        'reversedInReview': calibration.get('reversedInReview', 0),
        'correctionCount': calibration.get('correctionNotes', 0),
        'trainingGapCount': len(policy_graph.get('trainingGaps', [])),
    }
    completion = {
        'sessionId': session_id,
        'completedAt': now_iso(),
        'sessionMode': preferences.get('metadata', {}).get('sessionMode'),
        'intakePath': preferences.get('metadata', {}).get('intakePath'),
        'accountId': preferences.get('metadata', {}).get('accountId'),
        'accountLabel': preferences.get('metadata', {}).get('accountLabel'),
        'swipeCount': len(swipes),
        'savedLocally': True,
        'preferencesPath': str(prefs_path),
        'policyBriefPath': artifact_paths['policyBrief'],
        'policyGraphPath': artifact_paths['policyGraph'],
        'calibrationPath': artifact_paths['calibration'],
        'trainingPackPath': str(output_dir / 'training-pack.json'),
        'analysisSummaryPath': str(output_dir / 'analysis-summary.json'),
        'scoreSummary': score_summary,
    }
    history = append_session_history(completion)
    score_trend = compute_score_trend(history.get('sessions', []))
    completion['scoreTrend'] = score_trend
    write_session_completion(completion)
    if runtime and runtime.get('sessionId') == session_id:
        update_runtime_status('completed', completedAt=completion['completedAt'])

    return {
        'ok': True,
        'paths': {
            'preferences': str(prefs_path),
            'trainingPack': str(output_dir / 'training-pack.json'),
            'policyGraph': artifact_paths['policyGraph'],
            'calibration': artifact_paths['calibration'],
            'policyBrief': artifact_paths['policyBrief'],
            'analysisSummary': str(output_dir / 'analysis-summary.json'),
        },
        'summaryHeadline': headline,
        'briefHeadline': brief_first_line,
        'policyBriefUrl': '/api/policy-brief',
        'swipeCount': len(swipes),
        'sessionId': session_id,
        'scoreSummary': score_summary,
        'scoreTrend': score_trend,
        'sessionStatus': build_session_status(),
    }


if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='Compile swipe training into all artifacts')
    parser.add_argument('preferences', nargs='?', help='Path to preferences.json')
    parser.add_argument('--save-settings', action='store_true')
    parser.add_argument('--output-dir', '-o', help='Output directory')
    args = parser.parse_args()

    prefs = Path(args.preferences) if args.preferences else USER_DIR / 'preferences.json'
    out = Path(args.output_dir) if args.output_dir else USER_DIR
    result = compile_training(prefs, out, save_settings_from_prefs=args.save_settings)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get('ok') else 1)
