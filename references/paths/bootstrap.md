# Bootstrap path

**Suggest when:** No prior training, no imported rules, user wants to learn from scratch or demo first.

## Agent script

1. Complete intake → `confirm bootstrap`
2. Ask deployment (desktop / phone on Wi‑Fi)
3. `setup-agent.py` if agent name not set
4. Fetch **30–50 representative emails** (mixed senders) or demo batch
5. Build batch:

```json
{
  "metadata": {
    "sessionMode": "bootstrap",
    "intakePath": "bootstrap"
  },
  "emails": []
}
```

6. `inject-emails.py batch.json` → `serve-ui.py`
7. Tell user gestures once; stay quiet during swiping
8. After session → `post-training-flow.md`

## Queue behavior

- Smart queue surfaces **uncertain senders** and urgent keywords
- **Always include `predictedAction` + `predictionConfidence` on every email** — even cold bootstrap. Guess keep / spam / important on every message so the score after the session reflects real agent accuracy. Low confidence is fine; a blank guess is not.

## Success

- `assistant-brief.md` lists learned domain/sender patterns
- `calibration.json` baseline for future refine sessions
- Agent enters **recommend-only** on new mail

## Example agent line

> "I'll load a broad sample of your inbox so you can teach me your defaults — left don't keep, right keep, double-tap important."
