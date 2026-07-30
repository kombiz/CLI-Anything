# Buzz CLI Harness Architecture

## Source Analysis

- Target: [block/buzz](https://github.com/block/buzz)
- Analyzed revision: `4253688bf05c21a066bc5a5dc928256163fd3451`
- Native package: Rust crate `buzz-cli`
- Native executable: `buzz`
- Native relay: the Buzz relay is the source of truth; remote operations use
  signed Nostr events and the relay's narrow HTTP/WebSocket surface.
- Native local format: persona-pack directories containing
  `.plugin/plugin.json` and `.persona.md` files.

Buzz already has an agent-first CLI. The harness therefore delegates to the real
Rust executable instead of reproducing relay or Nostr behavior in Python.

## GUI and Backend Mapping

| Buzz surface | Native CLI group |
|---|---|
| Managed agents | `agents managed` (local Desktop control), `agents draft-*` (owner review) |
| Messages and threads | `messages` |
| Channels and canvas | `channels`, `canvas` |
| Reactions and custom emoji | `reactions`, `emoji` |
| Direct messages and users | `dms`, `users` |
| Workflows and activity | `workflows`, `feed` |
| Social graph and knowledge notes | `social`, `notes` |
| Git collaboration | `repos`, `patches`, `issues`, `pr` |
| Media | `media`, `upload` |
| Agent memory | `mem` |
| Persona packs | `pack` |
| Community administration | `moderation` |

The harness exposes each native group as a transparent passthrough. Subcommands
remain owned and validated by Buzz's Clap definitions, so new native flags and
subcommands work without a Python release. `raw` is an additional
forward-compatibility escape hatch.

## Harness Responsibilities

1. Discover and invoke the real `buzz` executable without a shell.
2. Keep `BUZZ_PRIVATE_KEY` and `BUZZ_AUTH_TAG` environment-only. The wrapper
   rejects forwarding either value on the process command line.
3. Persist only non-secret local preferences: relay URL and native output format.
4. Use locked JSON writes and reversible local session changes.
5. Offer a default REPL and one-shot Click commands.
6. Add `--dry-run` planning that never starts the native process.
7. Preserve Buzz's exit codes and structured errors.
8. Provide JSON envelopes for agents while retaining readable native output for
   humans.

Managed-agent reads and lifecycle operations use Buzz's authenticated loopback
Desktop control service. The Desktop process remains the only component that
loads owner and agent keys. Native mutations emit a JSON approval plan by
default and require an explicit `--approve`; the Python harness forwards this
contract unchanged.

`agents managed provision-channel` is the transactional project bootstrap:
create a private channel, record the canonical repository context in its
canvas, create agents sequentially, attach each as a bot, and start them.
Failures trigger best-effort cleanup of agents created by that invocation and
then the new channel.

## State and Undo

The session file is local wrapper state, not a Buzz project:

```json
{
  "relay_url": "https://relay.example.com",
  "output_format": "compact",
  "history": [],
  "future": []
}
```

Undo and redo apply only to these local preferences. Remote Buzz mutations are
never represented as safely reversible.

Settings resolve in this order:

1. command-line option;
2. saved wrapper session;
3. native Buzz environment variable;
4. native Buzz default.

No key, auth tag, message content, event ID, or backend response is saved.

## Output and Error Contract

Without `--json`, the harness pretty-prints native JSON and passes native text
through unchanged. With `--json`, it emits an envelope containing:

- `ok`
- `backend`
- redacted `command`
- `exit_code`
- parsed `data` or `error`
- `stderr` when relevant

Buzz exit codes are preserved: `0` success, `1` input/not-found, `2`
network/relay, `3` authentication, `4` other, and `5` write conflict.

## Preview Decision

No CLI-Anything preview bundle is implemented. Buzz's useful state is structured
relay data or persona-pack inspection text, not a renderable project snapshot.
The native read commands and desktop application remain the truthful inspection
surfaces.

## Test Strategy

Unit tests cover session locking, precedence, secret rejection, native argument
construction, output parsing, and subprocess behavior.

Real-backend E2E tests invoke the installed native `buzz` executable to validate
and inspect synthetic persona packs. Live relay mutations are intentionally
excluded because safe coverage requires a disposable relay, Postgres, Redis, and
synthetic Nostr credentials.
