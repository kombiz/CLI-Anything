from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cli_anything.buzz import buzz_cli
from cli_anything.buzz.core.commands import (
    GROUP_HELP,
    NATIVE_GROUPS,
    build_native_args,
    dry_run_payload,
    ensure_no_secret_args,
    parse_stderr,
    parse_stdout,
    redact_args,
)
from cli_anything.buzz.core.session import (
    SESSION_HISTORY_LIMIT,
    SessionState,
    SessionStore,
    resolve_settings,
    validate_relay_url,
)
from cli_anything.buzz.utils.buzz_backend import (
    DEFAULT_BUZZ_TIMEOUT,
    find_buzz,
    parse_root_commands,
    run_buzz,
)


# Session tests (10)


def test_session_loads_defaults_when_missing(tmp_path: Path) -> None:
    state = SessionStore(tmp_path / "missing.json").load()
    assert state.relay_url is None
    assert state.output_format == "json"
    assert state.history == []


def test_session_save_and_load_round_trip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    state = SessionState(relay_url="https://relay.example.com", output_format="compact")
    saved = store.save(state)
    loaded = store.load()
    assert saved == store.path
    assert loaded.snapshot() == state.snapshot()


def test_session_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="not a JSON object"):
        SessionStore(path).load()


def test_session_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed Buzz session JSON"):
        SessionStore(path).load()


def test_session_rejects_malformed_history_entry(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text('{"history":["invalid"]}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"history\[0\].*JSON object"):
        SessionStore(path).load()


def test_session_mutation_records_history(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    state = SessionState()
    store.mutate(state, relay_url="https://relay.example.com")
    assert state.relay_url == "https://relay.example.com"
    assert state.history == [{"relay_url": None, "output_format": "json"}]


def test_session_undo_and_redo(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    state = SessionState()
    store.mutate(state, output_format="compact")
    store.undo(state)
    assert state.output_format == "json"
    store.redo(state)
    assert state.output_format == "compact"


def test_session_new_mutation_clears_redo(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    state = SessionState()
    store.mutate(state, output_format="compact")
    store.undo(state)
    store.mutate(state, relay_url="https://relay.example.com")
    assert state.future == []


def test_session_history_is_bounded(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "session.json")
    state = SessionState()
    for index in range(SESSION_HISTORY_LIMIT + 25):
        store.mutate(state, output_format="compact" if index % 2 else "json")
    assert len(state.history) == SESSION_HISTORY_LIMIT


def test_session_serialization_never_contains_credentials(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    store = SessionStore(path)
    store.save(SessionState(relay_url="https://relay.example.com"))
    text = path.read_text(encoding="utf-8")
    assert "private_key" not in text
    assert "auth_tag" not in text
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_setting_precedence_is_cli_then_session_then_env() -> None:
    state = SessionState(
        relay_url="https://saved.example.com",
        output_format="compact",
    )
    assert resolve_settings(
        "https://cli.example.com",
        "json",
        state,
        {"BUZZ_RELAY_URL": "https://env.example.com"},
    ) == ("https://cli.example.com", "json")
    assert resolve_settings(
        None,
        None,
        state,
        {"BUZZ_RELAY_URL": "https://env.example.com"},
    ) == ("https://saved.example.com", "compact")
    assert resolve_settings(
        None,
        None,
        SessionState(),
        {"BUZZ_RELAY_URL": "https://env.example.com"},
    ) == ("https://env.example.com", "json")


def test_relay_url_validation_rejects_credentials_and_bad_schemes() -> None:
    assert (
        validate_relay_url("https://relay.example.com/") == "https://relay.example.com"
    )
    with pytest.raises(ValueError, match="absolute"):
        validate_relay_url("relay.example.com")
    with pytest.raises(ValueError, match="embedded credentials"):
        validate_relay_url("https://user:pass@relay.example.com")


def test_raw_relay_url_credentials_are_rejected() -> None:
    with pytest.raises(ValueError, match="embedded credentials"):
        ensure_no_secret_args(
            ("messages", "get", "--relay", "https://user:secret@relay.example.com")
        )


def test_agents_help_matches_native_description() -> None:
    assert GROUP_HELP["agents"] == "Draft owner-reviewed agent creation and updates."


# Command tests (8)


def test_build_native_args_orders_global_flags_before_group() -> None:
    assert build_native_args(
        "messages",
        ("get", "--channel", "abc"),
        relay_url="https://relay.example.com",
        output_format="compact",
    ) == [
        "--relay",
        "https://relay.example.com",
        "--format",
        "compact",
        "messages",
        "get",
        "--channel",
        "abc",
    ]


def test_native_inventory_contains_all_21_groups() -> None:
    assert len(NATIVE_GROUPS) == 21
    assert {"messages", "pack", "moderation", "repos"} <= set(NATIVE_GROUPS)


def test_secret_forwarding_is_rejected() -> None:
    for flag in ("--private-key", "--auth-tag"):
        with pytest.raises(ValueError, match="environment"):
            ensure_no_secret_args(("messages", "get", flag, "secret"))


def test_secret_arguments_are_redacted() -> None:
    assert redact_args(
        ("buzz", "--private-key", "secret", "--auth-tag=owner-secret", "channels")
    ) == [
        "buzz",
        "--private-key",
        "<redacted>",
        "--auth-tag=<redacted>",
        "channels",
    ]


def test_parse_stdout_returns_structured_json() -> None:
    assert parse_stdout('{"accepted":true,"event_id":"abc"}') == {
        "accepted": True,
        "event_id": "abc",
    }


def test_parse_stdout_preserves_plain_text() -> None:
    assert parse_stdout("Valid.\n") == "Valid."


def test_parse_stderr_finds_buzz_json_error() -> None:
    assert parse_stderr(
        'diagnostic\n{"error":"auth_error","message":"missing","retryable":false}\n'
    ) == {
        "error": "auth_error",
        "message": "missing",
        "retryable": False,
    }


def test_dry_run_plan_does_not_claim_execution() -> None:
    payload = dry_run_payload("/usr/bin/buzz", ["messages", "get"])
    assert payload["executed"] is False
    assert payload["dry_run"] is True
    assert payload["command"] == ["/usr/bin/buzz", "messages", "get"]


def test_managed_agent_approval_contract_is_forwarded_unchanged() -> None:
    proposed = build_native_args(
        "agents",
        (
            "managed",
            "create",
            "--name",
            "Docs-Codex",
            "--agent-command",
            "codex",
        ),
        relay_url=None,
        output_format="json",
    )
    approved = [*proposed, "--approve"]
    assert proposed == [
        "--format",
        "json",
        "agents",
        "managed",
        "create",
        "--name",
        "Docs-Codex",
        "--agent-command",
        "codex",
    ]
    assert approved[-1] == "--approve"


def test_managed_channel_provisioning_preserves_repeated_agent_specs() -> None:
    native_args = build_native_args(
        "agents",
        (
            "managed",
            "provision-channel",
            "--name",
            "dokploy",
            "--context",
            "/srv/dokploy",
            "--agent",
            "Dokploy-Codex=codex",
            "--agent",
            "Dokploy-Claude=claude",
            "--approve",
        ),
        relay_url=None,
        output_format="json",
    )
    assert native_args[-5:] == [
        "--agent",
        "Dokploy-Codex=codex",
        "--agent",
        "Dokploy-Claude=claude",
        "--approve",
    ]
    assert native_args.count("--agent") == 2


# Backend tests (6)


def _make_fake_buzz(tmp_path: Path) -> Path:
    script = tmp_path / "buzz"
    script.write_text(
        """#!/bin/sh
if [ "$1" = "--help" ]; then
  printf 'Commands:\\n  messages  Message commands\\n  pack      Pack commands\\n\\nOptions:\\n'
  exit 0
fi
if [ "$1" = "stdin" ]; then
  read line
  printf '{"stdin":"%s"}\\n' "$line"
  exit 0
fi
if [ "$1" = "fail" ]; then
  printf '{"error":"user_error","message":"bad"}\\n' >&2
  exit 5
fi
printf '{"args":"%s"}\\n' "$*"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_find_buzz_uses_explicit_executable(tmp_path: Path) -> None:
    script = _make_fake_buzz(tmp_path)
    assert find_buzz(str(script)) == str(script.resolve())


def test_find_buzz_fails_loudly_for_missing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not usable"):
        find_buzz(str(tmp_path / "missing"))


def test_backend_invokes_without_shell_and_captures_output(tmp_path: Path) -> None:
    script = _make_fake_buzz(tmp_path)
    result = run_buzz(["hello", "two words"], executable=str(script))
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"args": "hello two words"}


def test_backend_passes_standard_input(tmp_path: Path) -> None:
    script = _make_fake_buzz(tmp_path)
    result = run_buzz(["stdin"], executable=str(script), input_text="hello\n")
    assert json.loads(result.stdout) == {"stdin": "hello"}


def test_backend_preserves_nonzero_exit_and_stderr(tmp_path: Path) -> None:
    script = _make_fake_buzz(tmp_path)
    result = run_buzz(["fail"], executable=str(script))
    assert result.returncode == 5
    assert json.loads(result.stderr) == {"error": "user_error", "message": "bad"}


def test_backend_timeout_is_bounded(tmp_path: Path) -> None:
    script = tmp_path / "buzz"
    script.write_text("#!/bin/sh\nsleep 2\n", encoding="utf-8")
    script.chmod(0o755)
    with pytest.raises(subprocess.TimeoutExpired):
        run_buzz(["hang"], executable=str(script), timeout=0.01)


def test_backend_uses_default_timeout_when_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _make_fake_buzz(tmp_path)
    observed: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.delenv("CLI_ANYTHING_BUZZ_TIMEOUT", raising=False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    run_buzz(["hello"], executable=str(script))
    assert observed["timeout"] == DEFAULT_BUZZ_TIMEOUT


def test_repl_returns_to_prompt_after_command_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _make_fake_buzz(tmp_path)
    lines = iter(["raw messages get", "session status", "quit"])
    warnings: list[str] = []
    goodbyes: list[bool] = []

    class FakeSkin:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def print_banner(self) -> None:
            pass

        def info(self, message: str) -> None:
            pass

        def create_prompt_session(self) -> None:
            return None

        def get_input(self, *args: object, **kwargs: object) -> str:
            return next(lines)

        def warning(self, message: str) -> None:
            warnings.append(message)

        def error(self, message: str) -> None:
            pytest.fail(f"unexpected REPL error: {message}")

        def print_goodbye(self) -> None:
            goodbyes.append(True)

    def interrupted_run(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(buzz_cli, "ReplSkin", FakeSkin)
    monkeypatch.setattr(buzz_cli, "run_buzz", interrupted_run)
    result = buzz_cli.cli.main(
        args=["--buzz-binary", str(script)],
        prog_name="cli-anything-buzz",
        standalone_mode=False,
    )
    assert result is None
    assert warnings == ["Command interrupted"]
    assert goodbyes == [True]


def test_parse_native_root_help_inventory(tmp_path: Path) -> None:
    script = _make_fake_buzz(tmp_path)
    result = run_buzz(["--help"], executable=str(script))
    assert parse_root_commands(result.stdout) == ["messages", "pack"]
