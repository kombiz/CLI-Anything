# CLI-Anything Buzz Test Plan

## Test Inventory Plan

- `test_core.py`: 33 unit tests planned.
- `test_full_e2e.py`: 20 real-backend and installed-command tests planned.

## Unit Test Plan

### `core/session.py` — 10 tests

- Load defaults when no session file exists.
- Save and load relay URL and native output format.
- Reject non-object and malformed session JSON.
- Update relay and format while recording undo history.
- Undo and redo local configuration changes.
- Clear redo history after a new mutation.
- Reset local configuration.
- Persist with the locked JSON writer.
- Ensure serialized state contains no private key or auth tag fields.
- Resolve command-line, session, environment, and native defaults in precedence order.
- Reject malformed history/future entries before undo or redo.
- Cap persisted undo/redo history at 100 snapshots.
- Preserve concurrent read-modify-write updates with atomic replacement.

### `core/commands.py` — 9 tests

- Build native Buzz argument vectors with relay and format globals in the correct position.
- Keep all 21 native command groups in the supported inventory.
- Reject `--private-key` and `--auth-tag` in forwarded arguments.
- Redact secret-bearing arguments in diagnostics.
- Parse JSON stdout into structured data.
- Preserve plain-text stdout from local `pack` operations.
- Parse Buzz JSON errors from stderr.
- Build dry-run plans without invoking a subprocess.
- Forward the native managed-agent approval contract without rewriting flags.
- Forward a multi-agent channel-provision plan, including repeated agent specs
  and the explicit approval switch, without changing argument order.

### `utils/buzz_backend.py` — 6 tests

- Discover an explicit Buzz executable.
- Fail loudly when no real Buzz executable exists.
- Invoke the backend without a shell.
- Pass standard input through for Buzz commands that accept `-`.
- Preserve Buzz exit codes, stdout, and stderr.
- Parse the native root help into a command inventory.
- Apply the default timeout and allow an explicit timeout override.

## E2E Test Plan

The E2E suite requires the real `buzz` executable and fails if it is missing.
It uses only Buzz's local `pack` command group, so it neither requires
credentials nor mutates a relay.

### Real backend workflows

- Invoke `buzz --help` through the backend and verify the real command inventory.
- Create a synthetic persona-pack directory with `.plugin/plugin.json` and a
  `.persona.md` file.
- Validate the pack through the real native backend and verify the exact
  successful diagnostic.
- Inspect the pack through the real native backend and verify its resolved name,
  version, persona count, and persona identity.
- Validate an intentionally invalid pack and verify Buzz's non-zero exit code and
  structured error category.

### Installed CLI subprocess workflows

All subprocess tests resolve `cli-anything-buzz` with `_resolve_cli()` and do not
set a working directory.

- Verify root help and all wrapper command groups.
- Verify `backend status --json` reports the real executable without exposing
  credential values.
- Persist a relay profile, read it from a second process, then undo and redo it.
- Verify `--dry-run --json` returns the native command plan without executing it.
- Forward `pack validate` to the real Buzz binary and verify the JSON envelope.
- Forward `pack inspect` to the real Buzz binary and verify the resolved pack
  content.
- Verify forwarded private-key and auth-tag flags are rejected with instructions
  to use environment variables.
- Verify Click usage failures use exit code 1 and a JSON envelope under `--json`.
- Verify native timeouts use exit code 4 and a structured JSON error.
- Verify `raw`, `backend help`, and `session reset` forwarding.
- Drive the default REPL over stdin, including global-only input, session changes,
  raw forwarding, and clean exit without recursive REPL entry.
- Verify session write failures remain structured under `--json`.

## Realistic Workflow Scenarios

### Persona pack authoring check

- **Simulates:** An agent preparing a Buzz persona pack for desktop import.
- **Operations chained:** Create synthetic manifest and persona files, run
  `pack validate`, then run `pack inspect`.
- **Verified:** Native Buzz accepts the pack, resolves one persona, and reports
  the expected metadata and prompt identity.

### Relay profile switching

- **Simulates:** An agent switching between self-hosted Buzz communities without
  repeating the relay URL or storing a private key.
- **Operations chained:** Save a relay URL and compact format, inspect status,
  undo, redo, and reload from a new process.
- **Verified:** Locked session persistence, precedence rules, reversible local
  configuration, and absence of secret fields.

### Safe remote mutation planning

- **Simulates:** An agent reviewing a message-send command before contacting a
  relay.
- **Operations chained:** Run a forwarded `messages send` command with
  `--dry-run --json`.
- **Verified:** The plan contains the correctly ordered native command, reports
  that execution did not occur, and creates no remote side effect.

### Desktop-managed agent approval planning

- **Simulates:** An agent proposing a local Codex runtime without gaining
  implicit permission to mutate Buzz Desktop.
- **Operations chained:** Forward `agents managed create` once without approval,
  then construct the exact approved argument vector.
- **Verified:** The harness preserves the native plan-first contract and places
  `--approve` only in the explicitly approved invocation.

### Managed channel provisioning

- **Simulates:** Provisioning one project channel with a repository context,
  Codex, and Claude through the native Desktop control workflow.
- **Operations chained:** Forward channel name, context path, two repeated
  `NAME=COMMAND` agent specifications, start behavior, and final approval.
- **Verified:** Repeated agent specifications and `--approve` reach the native
  CLI unchanged so its sequential provisioning and cleanup policy remains the
  sole source of truth.

## Backend Scope and Safety

- The real native backend is mandatory.
- Live relay commands are not exercised because they require a disposable relay,
  Postgres, Redis, and synthetic Nostr credentials.
- Local persona-pack validation and inspection provide deterministic real-backend
  proof without account or network side effects.
- Tests never write or print a real `BUZZ_PRIVATE_KEY` or `BUZZ_AUTH_TAG`.

## Test Results

Command:

```bash
CLI_ANYTHING_FORCE_INSTALLED=1 \
  python -m pytest cli_anything/buzz/tests -v -s --tb=no
```

Output:

```text
============================= test session starts ==============================
platform linux -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0 -- /home/laddy/.local/share/mise/installs/python/latest/bin/python
cachedir: .pytest_cache
rootdir: /home/laddy/code/dev/CLI-Anything/buzz/agent-harness
plugins: anyio-4.14.2, cov-7.1.0, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... [_resolve_cli] Using installed command: /home/laddy/.local/share/mise/installs/python/latest/bin/cli-anything-buzz
collected 38 items

cli_anything/buzz/tests/test_core.py::test_session_loads_defaults_when_missing PASSED
cli_anything/buzz/tests/test_core.py::test_session_save_and_load_round_trip PASSED
cli_anything/buzz/tests/test_core.py::test_session_rejects_non_object_json PASSED
cli_anything/buzz/tests/test_core.py::test_session_rejects_malformed_json PASSED
cli_anything/buzz/tests/test_core.py::test_session_mutation_records_history PASSED
cli_anything/buzz/tests/test_core.py::test_session_undo_and_redo PASSED
cli_anything/buzz/tests/test_core.py::test_session_new_mutation_clears_redo PASSED
cli_anything/buzz/tests/test_core.py::test_session_serialization_never_contains_credentials PASSED
cli_anything/buzz/tests/test_core.py::test_setting_precedence_is_cli_then_session_then_env PASSED
cli_anything/buzz/tests/test_core.py::test_relay_url_validation_rejects_credentials_and_bad_schemes PASSED
cli_anything/buzz/tests/test_core.py::test_build_native_args_orders_global_flags_before_group PASSED
cli_anything/buzz/tests/test_core.py::test_native_inventory_contains_all_21_groups PASSED
cli_anything/buzz/tests/test_core.py::test_secret_forwarding_is_rejected PASSED
cli_anything/buzz/tests/test_core.py::test_secret_arguments_are_redacted PASSED
cli_anything/buzz/tests/test_core.py::test_parse_stdout_returns_structured_json PASSED
cli_anything/buzz/tests/test_core.py::test_parse_stdout_preserves_plain_text PASSED
cli_anything/buzz/tests/test_core.py::test_parse_stderr_finds_buzz_json_error PASSED
cli_anything/buzz/tests/test_core.py::test_dry_run_plan_does_not_claim_execution PASSED
cli_anything/buzz/tests/test_core.py::test_managed_agent_approval_contract_is_forwarded_unchanged PASSED
cli_anything/buzz/tests/test_core.py::test_managed_channel_provisioning_preserves_repeated_agent_specs PASSED
cli_anything/buzz/tests/test_core.py::test_find_buzz_uses_explicit_executable PASSED
cli_anything/buzz/tests/test_core.py::test_find_buzz_fails_loudly_for_missing_explicit_path PASSED
cli_anything/buzz/tests/test_core.py::test_backend_invokes_without_shell_and_captures_output PASSED
cli_anything/buzz/tests/test_core.py::test_backend_passes_standard_input PASSED
cli_anything/buzz/tests/test_core.py::test_backend_preserves_nonzero_exit_and_stderr PASSED
cli_anything/buzz/tests/test_core.py::test_parse_native_root_help_inventory PASSED
cli_anything/buzz/tests/test_full_e2e.py::test_real_backend_root_inventory_matches_wrapper PASSED
cli_anything/buzz/tests/test_full_e2e.py::test_real_backend_validates_synthetic_persona_pack PASSED
cli_anything/buzz/tests/test_full_e2e.py::test_real_backend_inspects_resolved_persona_pack PASSED
cli_anything/buzz/tests/test_full_e2e.py::test_real_backend_rejects_invalid_persona_pack PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_help_lists_all_domains PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_backend_status_is_secret_safe PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_session_round_trip_undo_and_redo PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_dry_run_does_not_contact_relay PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_forwards_pack_validate PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_forwards_pack_inspect PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_rejects_private_key_argument PASSED
cli_anything/buzz/tests/test_full_e2e.py::TestCLISubprocess::test_installed_cli_rejects_auth_tag_argument PASSED

============================== 38 passed in 0.65s ==============================
```

## Summary Statistics

- Total: 38
- Passed: 38
- Failed: 0
- Pass rate: 100%
- Runtime: 0.74 seconds
- Installed-command proof:
  `/home/laddy/.local/share/mise/installs/python/latest/bin/cli-anything-buzz`

## Coverage Notes

- Covered: local session state, locked persistence, undo/redo, setting
  precedence, secret handling, all native root domains, dry-run planning,
  installed CLI resolution, native help, and real persona-pack validation and
  inspection.
- Not covered: live relay reads/writes, Nostr signing, media transfer, and
  conflict behavior. Those require a disposable Buzz relay with Postgres,
  Redis, and synthetic credentials.
- No preview bundle is tested because the harness does not expose a preview
  producer.

## Review Remediation Results

Command:

```bash
python -m pytest agent-harness/cli_anything/buzz/tests -q
```

Output:

```text
.....................................................                    [100%]
53 passed
```

The added coverage exercises structured Click failures, native timeouts, raw
and backend-help forwarding, session reset and write failures, malformed and
bounded history, concurrent updates, credential-bearing raw relay URLs, and the
piped default REPL including interruption recovery, its global-only recursion
guard, and session refresh. Native help drift and the backend's omitted-timeout
default are also covered directly.
