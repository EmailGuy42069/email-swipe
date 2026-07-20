# Autonomy tiers

How much your agent can do without asking each time. **Email Swipe never auto-deletes mail at any tier.**

| Tier | `settings.agent.autonomyLevel` | Behavior |
|------|-------------------------------|----------|
| **Recommend** (default) | `recommend` | Suggest labels, folders, and actions in chat. User approves before mailbox changes. |
| **Approve batch** | `approve_batch` | Agent may propose a batch of safe actions and wait for one approval. No delete or skip-inbox without user. |
| **Auto safe** | `auto_safe` | Agent may apply only narrow, trained rules within `platformRules.forbiddenActions`. User must enable explicitly in UI. |

## Where it is set

- **UI:** Advanced settings → Agent → Autonomy level (confirmation required above Recommend).
- **Compile:** Written to `policy-graph.json` as `defaultAutonomyLevel` on save/compile.
- **Agent:** Should read `get_policy_graph` — do not override without user intent.

## Hard limits (all tiers)

- `never_auto_delete`
- `never_skip_inbox_without_approval` (when `platformRules.neverRemoveFromInbox` is on)

See also [post-training-flow.md](./post-training-flow.md) and [ADVANCED-SETTINGS-SPEC.md](../docs/ADVANCED-SETTINGS-SPEC.md).
