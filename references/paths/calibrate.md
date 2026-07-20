# Calibrate path

**Suggest when:** User already has email rules (filters, labels, agent memory) and wants to refine — not retrain from zero.

## Agent script

1. Complete intake → `confirm calibrate`
2. **Import rules** (chat or existing files):

```bash
python scripts/seed_policy_graph.py rules-import.json
# or stdin / MCP compile after seed
```

`rules-import.json` shape:

```json
{
  "policies": [
    {
      "match": { "domain": "linkedin.com" },
      "action": "dont_keep",
      "reason": "User rule: promo job alerts"
    }
  ],
  "relationships": [
    {
      "match": { "sender": "hr@company.com" },
      "type": "important_sender",
      "reason": "User rule: HR always important"
    }
  ]
}
```

3. Present imported rules from `get_policy_brief` — user confirms or edits in chat
4. Scan recent inbox; score each message against `policy-graph.json`
5. Select **10–20 low-confidence** emails only (confidence &lt; 0.8 or conflicting rules)
6. Build batch with predictions:

```json
{
  "metadata": { "sessionMode": "calibrate", "intakePath": "calibrate" },
  "emails": [
    {
      "id": "msg-1",
      "sender": "Vendor",
      "from": "alex@vendor.com",
      "subject": "Quick question",
      "snippet": "...",
      "predictedAction": "spam",
      "predictionConfidence": 0.62,
      "agentNote": "Similar to promos you don't keep, but this sender sent important mail once."
    }
  ]
}
```

7. `inject-emails.py` → `serve-ui.py`
8. User corrects agent judgment on edge cases
9. `post-training-flow.md` — focus on **corrections**, not cold-start rules

## Queue behavior

- UI sorts by **low `predictionConfidence` first**
- Learning hints show agent guess when present
- **Guess on every email** in the batch — never omit `predictedAction` just because confidence is low

## Success

- Imported rules stay `userConfirmed: true`
- Calibration improves on previously uncertain senders
- Brief has "Ready to recommend" + fewer `trainingGaps`

## Example agent line

> "You already have rules — I'll import them, then we'll only swipe mail I'm not sure about."
