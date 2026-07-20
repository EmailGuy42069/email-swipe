# Learning audit log

Weekly template for measuring post-training quality. Copy a section per session; keep local (gitignored) if preferred.

## Session metadata

| Field | Value |
|-------|-------|
| Date | YYYY-MM-DD |
| Swipe count | |
| Agent delivery channel | MCP / API / file |
| Brief presented in chat? | yes / no |

## Calibration (from `calibration.json`)

| Metric | Value |
|--------|-------|
| Overall agreement | |
| Scorable predictions | |
| Correct | |
| Reversed in pile review | |
| Correction notes | |
| By action: don't keep | |
| By action: keep | |
| By action: important | |

## Policy accuracy

| Check | Result |
|-------|--------|
| User confirmed brief policies | yes / partial / no |
| Inconsistent senders flagged | count |
| Policies user rejected in chat | list |
| Victory pile reversals logged | count |

## Agent integration friction

| Channel | Works? | Notes |
|---------|--------|-------|
| MCP `get_policy_brief` | | |
| GET `/api/policy-brief` | | |
| File read `assistant-brief.md` | | |
| Auto-compile on POST | | |

## Comprehension (user trust)

After agent reads brief aloud:

- "Do you trust these rules?" (1–5):
- What was confusing?
- Preferred section order?

## Decisions / follow-ups

- Threshold changes needed?
- Training gaps to address?
- Skip victory UI brief? (if MCP path sufficient)

---

## Integration test checklist

Run after each release:

```bash
# 1. Start UI server
python scripts/serve-ui.py

# 2. POST sample preferences (or complete a swipe session)
python scripts/compile_training.py ~/.config/email-swipe/preferences.json

# 3. Verify artifacts exist
test -f ~/.config/email-swipe/assistant-brief.md
test -f ~/.config/email-swipe/policy-graph.json
test -f ~/.config/email-swipe/calibration.json

# 4. API smoke test (server running)
# 4. API smoke test (server running — use Desktop URL from serve-ui or runtime.json)
DESKTOP_URL=$(python3 -c "import json; from pathlib import Path; p=Path.home()/'.config/email-swipe/runtime.json'; print(json.load(open(p)).get('desktopUrl','http://localhost:PORT'))")
curl -s "$DESKTOP_URL/api/policy-brief" | head -5
curl -s "$DESKTOP_URL/api/training-pack" | python3 -m json.tool | head -20

# 5. MCP tools (stdio — send initialize + tools/list manually or via client)
python scripts/watch-preferences.py
```

Log results in the table above.
