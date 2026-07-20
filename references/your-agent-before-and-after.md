# Your agent: before and after Email Swipe

A plain-language guide for humans. Your agent should walk you through the technical steps — this is what changes for **you**.

## Before

Your AI agent can read email if you connect it, but it does not **know your sorting rules**:

- Promotional mail might get the same attention as mail from your boss
- It cannot explain *your* "don't keep" vs "keep" vs "important" boundaries
- Each conversation starts from scratch unless you repeat preferences

You still use Gmail, Apple Mail, or Outlook exactly as today. Nothing about reading mail changes yet.

## Training (15–30 minutes per inbox)

You teach preferences one of four ways:

| Path | You do |
|------|--------|
| **Bootstrap** | Swipe a sample of real (or demo) mail |
| **Calibrate** | Swipe only mail your agent was unsure about |
| **Refine** | Short session on gaps from last time |
| **Import sorting** | Agent learns from folders you already use — no swiping |

**Multiple mailboxes?** Turn on **Unified inbox** in **Advanced settings**, read the guide, then train **one account at a time**. Same UI — a badge shows which mailbox you are training.

## After training (day 1)

You get artifacts on your machine (`~/.config/email-swipe/`):

- **assistant-brief.md** — plain English summary you read with your agent
- **policy-graph.json** — structured rules the agent uses at runtime
- **platform-rules.json** — label/folder *suggestions* (not auto-applied)

Your agent reads the brief with you and asks: *"Does this match how you want mail handled?"*

**Important:** Training does **not** automatically clean your inbox. Your mail apps look the same until you (or your agent, with approval) apply labels, filters, or archive actions.

## After training (week 1 and beyond)

This is where value compounds:

1. **Morning triage** — Ask your agent what needs you today. It uses your rules + fresh fetches from your mail tools.
2. **Recommend-only** — By default the agent *suggests*; you approve. No silent delete or hide-from-inbox.
3. **Refine when needed** — Wrong call on a sender? Note it in chat or run a short refine session.
4. **Score trend** — After multiple sessions, see whether agent agreement is improving.

## One inbox vs many

| Single inbox | Unified inbox (advanced) |
|--------------|--------------------------|
| Train once | Train each mailbox once |
| One brief | One brief with per-account sections |
| Agent fetches one account | Agent fetches each account, merges "needs you" in chat |

Start with your noisiest mailbox. Add others when ready.

## What Email Swipe is not

- Not a mail client replacement
- Not silent auto-archive
- Not a life-coaching interview (your agent may already know your calendar and projects — that's between you and your agent)
- Not cloud mail hosting

## Quick start

```bash
git clone https://github.com/EmailGuy42069/email-swipe.git
cd email-swipe
python scripts/serve-ui.py
```

Open the **Desktop URL** printed in the terminal. Demo mail loads if nothing was injected yet.

Full agent flow: [QUICKSTART.md](./QUICKSTART.md) · [AGENTS.md](../AGENTS.md)
