# Advanced folder routing

Three match modes — pick the right tool per folder.

## Match modes

| Mode | Types | Best for |
|------|-------|----------|
| **AI rule** | Plain-English descriptor | "All retail promotions even without the word sale" — **agent judges** |
| **Smart category** | Built-in intents (promotions, newsletters, …) | Pattern heuristics without writing rules |
| **Strict** | Keyword, domain, sender | Exact matches only — `promo` in subject, `@linkedin.com`, etc. |

## AI rule (descriptor)

User writes what belongs in the folder. The **agent** is the primary judge:

1. At **inject time**, agent scores each email against routes
2. UI shows agent confidence in the folder picker
3. At **runtime**, agent uses `aiRule` from `policy-graph` for new mail

### Inject with agent judgment

```json
{
  "id": "msg-1",
  "subject": "Summer styles you'll love",
  "from": "hello@brand.com",
  "snippet": "Discover our new collection",
  "folderJudgments": [
    {
      "routeId": "route-promotions",
      "confidence": 0.88,
      "reason": "Retail marketing — no transaction signals"
    }
  ]
}
```

Or single top pick:

```json
{
  "aiSuggestedFolderRouteId": "route-promotions",
  "aiSuggestedFolderConfidence": 0.88,
  "aiSuggestedFolderReason": "Marketing blast, not a receipt"
}
```

### Settings

```json
{
  "id": "route-promotions",
  "name": "Promotions",
  "matchType": "descriptor",
  "matchMode": "ai",
  "aiRule": "Retail promos, flash sales, and marketing blasts — even when they never say sale or promo"
}
```

## Smart category (intent)

Predefined signals — no agent call required for basic suggestions. Agent can still enrich with `folderIntent` / `folderHints`.

## Strict

Exact keyword, domain, or sender. Score is 100% or 0%. Use for hard rules:

```json
{
  "name": "LinkedIn",
  "matchType": "domain",
  "matchMode": "strict",
  "matchValue": "linkedin.com"
}
```

## Agent responsibilities

| Mode | Agent at inject | Agent at runtime |
|------|-----------------|------------------|
| AI rule | **Required** — set `folderJudgments` | Read `aiRule`, recommend folder |
| Smart category | Optional hints | Heuristics + hints |
| Strict | Not needed | Apply exact rule only |

## Swipe record

```json
{
  "folderRoute": {
    "folderName": "Promotions",
    "matchType": "descriptor",
    "matchMode": "ai",
    "aiRule": "Retail promos…",
    "matchScore": 0.88,
    "matchReason": "agent judged",
    "judgmentSource": "agent"
  }
}
```

`judgmentSource`: `agent` | `heuristic` | `strict`

## Persistence & building out the platform

Advanced routes are **remembered automatically**. Whenever the UI saves
(`POST /api/preferences`) or you run `compile_training`, the settings — including
`folders.advancedRoutingEnabled` and every route — are merged into
`~/.config/email-swipe/settings.json`. You do **not** need to re-ask for them each
session; read them from `settings.json` or from the compiled artifacts.

After each compile, the routes are surfaced in three places for you to act on:

| Artifact | Where routes appear | Use |
|----------|--------------------|-----|
| `settings.json` | `folders.routes` | Source of truth / persistent memory |
| `policy-graph.json` | `folderRoutingPolicies` (`folder_route_definition`) | Full match rules (aiRule, intent, strict) |
| `platform-rules.json` | `folderRoutes[]` with `howToBuild` | Build these out in the email platform |
| `training-pack.json` | `folderRoutes[]` | Slim runtime slice |

**Building out in the email platform:** for each entry in
`platform-rules.folderRoutes`, create the corresponding label/folder and route
matching mail to it. Respect the flags:

- `preservesInbox: true` → label/folder only; do **not** skip-inbox or archive.
- `requiresUserConfirmation: true` → confirm with the user before creating.
- `requiresAgentJudgment: true` (AI rules) → you classify each message; there is
  no exact filter to hand the platform, so run it as a recommend-time rule.
- Inbox-action routes (`action: keep|important|spam`) are training signals, not
  folders — they are excluded from `folderRoutes` and never become platform filters.
