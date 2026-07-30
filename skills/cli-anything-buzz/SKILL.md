---
name: "cli-anything-buzz"
description: Operate Block's Buzz collaboration platform through its real native Rust CLI with secret-safe relay profiles, JSON envelopes, dry-run planning, and a default REPL.
---

# CLI-Anything Buzz

Use `cli-anything-buzz` when an agent needs to inspect or operate a Buzz relay,
work with local Buzz persona packs, or plan a Buzz mutation without executing
it. The harness delegates to the native `buzz` executable; it does not
reimplement Nostr, relay, persona, or validation behavior.

## Prerequisites

- Python 3.10+
- The native `buzz` executable from <https://github.com/block/buzz>
- `BUZZ_PRIVATE_KEY` for relay operations
- `BUZZ_AUTH_TAG` only when owner attestation is required

Install the native backend from a Buzz source checkout:

```bash
cargo install --path crates/buzz-cli
```

Install the harness from this repository:

```bash
python -m pip install -e buzz/agent-harness
```

Verify the runtime before doing work:

```bash
cli-anything-buzz --json backend status
cli-anything-buzz --json backend commands
```

## Invocation Rules

Put harness options before the native Buzz domain:

```bash
cli-anything-buzz --json messages get --channel UUID
cli-anything-buzz --relay https://relay.example.com --format compact channels list
```

Native subcommand flags are passed through unchanged. Inspect native help at any
depth:

```bash
cli-anything-buzz messages --help
cli-anything-buzz backend help messages send
```

Run `cli-anything-buzz` with no subcommand to enter the stateful REPL.

## Native Domains

- `agents managed` — list and plan/approve local Desktop-managed agent lifecycle
- `agents draft-*` — draft owner-reviewed agent creation and updates
- `messages` — send, read, search, edit, delete, thread, diff, and vote
- `channels`, `canvas` — channel lifecycle, membership, metadata, and canvas
- `reactions`, `emoji` — reactions and workspace emoji
- `dms`, `users` — direct messages, profiles, and presence
- `workflows`, `feed` — workflow definitions/runs and activity
- `social`, `notes` — social graph and long-form knowledge notes
- `repos`, `patches`, `issues`, `pr` — NIP-34 git collaboration
- `media`, `upload` — Blossom media transfer
- `mem` — persistent agent engrams
- `pack` — local persona-pack validation and inspection
- `moderation` — reports, restrictions, and audit
- `raw` — forward a future native group not yet in the wrapper inventory

## Credentials and Safety

Never pass `--private-key` or `--auth-tag`. The harness rejects both forms,
including `--flag=value`, so values do not enter process listings, dry-run
plans, or local session state.

```bash
export BUZZ_PRIVATE_KEY='nsec1...'
export BUZZ_AUTH_TAG='[...]'  # only if required
```

For `agents managed create/start/stop/restart`, omit `--approve` first and
inspect the native JSON plan. Add `--approve` only after the plan is accepted.
These commands authenticate to the running Desktop through its owner-readable
loopback descriptor and do not require `BUZZ_PRIVATE_KEY`.

Provision a project channel and roster:

```bash
cli-anything-buzz --json agents managed provision-channel \
  --name dokploy \
  --context ~/code/greymatter/greymatter/dokploy \
  --agent Dokploy-Codex=codex \
  --agent Dokploy-Claude=claude
```

The first call is a no-op plan. Rerun with `--approve` to create the private
channel, write the context canvas, attach the agents sequentially, and start
them. On a later-stage failure, the native CLI attempts to remove agents
created by that invocation and then delete the new channel.

The session stores only a relay URL and native output format:

```bash
cli-anything-buzz --json session set-relay https://relay.example.com
cli-anything-buzz --json session set-format compact
cli-anything-buzz --json session status
cli-anything-buzz --json session undo
cli-anything-buzz --json session redo
```

Undo and redo affect local preferences only. They do not reverse relay
mutations.

Before a write, use dry-run to inspect the exact redacted native command:

```bash
cli-anything-buzz --dry-run --json \
  messages send --channel UUID --content "Status update"
```

A dry-run result includes `"executed": false` and never starts Buzz.

## Agent Workflows

Read messages:

```bash
cli-anything-buzz --json messages get --channel UUID --limit 20
cli-anything-buzz --json messages thread --channel UUID --event EVENT_ID
```

Send content safely through standard input:

```bash
cli-anything-buzz --json messages send --channel UUID --content - < message.md
```

Validate and inspect a local persona pack without relay credentials:

```bash
cli-anything-buzz --json pack validate /absolute/path/to/pack
cli-anything-buzz --json pack inspect /absolute/path/to/pack
```

Inspect a saved relay profile:

```bash
cli-anything-buzz --json session status
cli-anything-buzz --json backend status --check-relay
```

## JSON and Errors

Use the global `--json` option for programmatic calls. Success envelopes contain:

- `ok`
- `backend`
- redacted `command`
- `exit_code`
- parsed `data`

Failure envelopes are written to stderr. Preserve native Buzz exit semantics:

- `0` success
- `1` bad input or not found
- `2` network or relay failure
- `3` authentication failure
- `4` other backend failure
- `5` write conflict

Do not blindly retry exit `2` after a non-idempotent command: Buzz may report an
unknown delivery outcome. Inspect the native structured error first.

## Preview

This harness has no preview-bundle producer. Use Buzz's structured read commands,
persona-pack inspection, or the Buzz desktop client for truthful inspection.
