# Refine path

**Suggest when:** Prior Email Swipe training exists; `calibration.json` or `policy-graph.trainingGaps` show weak areas.

## Agent script

1. Complete intake → `confirm refine`
2. `get_calibration` + `get_policy_graph`
3. Name the gap aloud:

> "You're inconsistent on vendor@sales.com and promotional domains — let's do a short session on those."

4. Fetch **5–15 emails** targeting the gap (same sender/domain/category)
5. Build batch:

```json
{
  "metadata": {
    "sessionMode": "refine",
    "intakePath": "refine",
    "focusGap": "inconsistent_sender",
    "focusMatch": { "sender": "vendor@sales.com" }
  },
  "emails": []
}
```

6. `inject-emails.py` → `serve-ui.py`
7. Short swipe session → recompile → compare calibration before/after

## Queue behavior

- Focused queue (all emails from gap set)
- **Always include `predictedAction` + `predictionConfidence` on every email** (from prior policy-graph or a best guess)

## Success

- `trainingGaps` count drops
- `overall.agreement` improves
- Agent may suggest **bootstrap** again only if user wants full reset

## Example agent line

> "Last time we flagged a few senders I wasn't sure about — I pulled 8 more like those for a quick refine round."
