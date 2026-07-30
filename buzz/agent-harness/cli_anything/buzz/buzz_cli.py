#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import click

from cli_anything.buzz import __version__
from cli_anything.buzz.core.commands import (
    GROUP_HELP,
    NATIVE_GROUPS,
    build_native_args,
    dry_run_payload,
    ensure_no_secret_args,
    parse_stdout,
    result_payload,
)
from cli_anything.buzz.core.session import (
    NATIVE_DEFAULT_RELAY,
    SessionState,
    SessionStore,
    resolve_settings,
    validate_relay_url,
)
from cli_anything.buzz.utils.buzz_backend import (
    check_relay_liveness,
    find_buzz,
    native_command_inventory,
    run_buzz,
)
from cli_anything.buzz.utils.repl_skin import ReplSkin


PROXY_CONTEXT = {
    "ignore_unknown_options": True,
    "allow_extra_args": True,
}


@dataclass
class AppContext:
    use_json: bool
    dry_run: bool
    session_store: SessionStore
    state: SessionState
    relay_url: str | None
    output_format: str
    buzz_binary: str | None


def _json_echo(value: Any, *, err: bool = False) -> None:
    click.echo(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
        err=err,
    )


def _emit_value(app: AppContext, value: Any, *, human: str | None = None) -> None:
    if app.use_json:
        _json_echo(value)
        return
    if human is not None:
        click.echo(human)
    elif isinstance(value, (dict, list)):
        _json_echo(value)
    elif value is not None:
        click.echo(str(value))


def _fail(app: AppContext, message: str, *, exit_code: int = 1) -> None:
    if app.use_json:
        _json_echo(
            {
                "ok": False,
                "error": {
                    "error": "wrapper_error",
                    "message": message,
                    "retryable": False,
                },
                "exit_code": exit_code,
            },
            err=True,
        )
    else:
        click.echo(f"Error: {message}", err=True)
    raise click.exceptions.Exit(exit_code)


def _native_executable(app: AppContext) -> str:
    try:
        return find_buzz(app.buzz_binary)
    except RuntimeError as exc:
        _fail(app, str(exc), exit_code=4)
    raise AssertionError("unreachable")


def _run_native_args(app: AppContext, native_args: Sequence[str]) -> None:
    try:
        ensure_no_secret_args(native_args)
    except ValueError as exc:
        _fail(app, str(exc), exit_code=1)
    executable = _native_executable(app)
    if app.dry_run:
        payload = dry_run_payload(executable, native_args)
        human = "Would run: " + shlex.join(payload["command"])
        _emit_value(app, payload, human=human)
        return
    try:
        result = run_buzz(native_args, executable=executable)
    except Exception as exc:
        _fail(app, f"Failed to start Buzz: {exc}", exit_code=4)
        return
    payload = result_payload(
        result.executable,
        result.args,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if app.use_json:
        _json_echo(payload, err=result.returncode != 0)
    else:
        parsed = parse_stdout(result.stdout)
        if parsed is not None:
            if isinstance(parsed, (dict, list)):
                _json_echo(parsed)
            else:
                click.echo(parsed)
        if result.stderr.strip():
            click.echo(result.stderr.rstrip(), err=True)
    if result.returncode:
        raise click.exceptions.Exit(result.returncode)


def _run_native_group(app: AppContext, group: str, args: Sequence[str]) -> None:
    try:
        native_args = build_native_args(
            group,
            args,
            relay_url=app.relay_url,
            output_format=app.output_format,
        )
    except ValueError as exc:
        _fail(app, str(exc), exit_code=1)
        return
    _run_native_args(app, native_args)


@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Emit a JSON wrapper envelope.")
@click.option(
    "--session",
    "session_path",
    type=click.Path(path_type=Path, dir_okay=False),
    envvar="CLI_ANYTHING_BUZZ_SESSION",
    help="Local non-secret session JSON path.",
)
@click.option("--relay", help="Buzz relay URL; overrides session and BUZZ_RELAY_URL.")
@click.option(
    "--format",
    "requested_format",
    type=click.Choice(["json", "compact"]),
    help="Native Buzz read format.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the native command or local session change without executing it.",
)
@click.option(
    "--buzz-binary",
    type=click.Path(path_type=Path, dir_okay=False),
    envvar="CLI_ANYTHING_BUZZ_BINARY",
    hidden=True,
)
@click.pass_context
def cli(
    ctx: click.Context,
    use_json: bool,
    session_path: Path | None,
    relay: str | None,
    requested_format: str | None,
    dry_run: bool,
    buzz_binary: Path | None,
) -> None:
    """Operate Buzz through its real native agent CLI.

    Native domain flags are passed through unchanged. Put wrapper options before
    the domain, for example:

    \b
      cli-anything-buzz --json messages get --channel UUID
      cli-anything-buzz --dry-run messages send --channel UUID --content Hello

    Credentials are environment-only: BUZZ_PRIVATE_KEY and BUZZ_AUTH_TAG.
    """
    store = SessionStore(session_path)
    try:
        state = store.load()
        relay_url, output_format = resolve_settings(
            relay,
            requested_format,
            state,
        )
    except ValueError as exc:
        temp = AppContext(
            use_json=use_json,
            dry_run=dry_run,
            session_store=store,
            state=SessionState(),
            relay_url=None,
            output_format="json",
            buzz_binary=str(buzz_binary) if buzz_binary else None,
        )
        _fail(temp, str(exc), exit_code=1)
        return
    ctx.obj = AppContext(
        use_json=use_json,
        dry_run=dry_run,
        session_store=store,
        state=state,
        relay_url=relay_url,
        output_format=output_format,
        buzz_binary=str(buzz_binary) if buzz_binary else None,
    )
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.group("backend")
def backend_group() -> None:
    """Inspect the real Buzz executable and relay."""


@backend_group.command("status")
@click.option("--check-relay", is_flag=True, help="Probe the relay's _liveness endpoint.")
@click.pass_obj
def backend_status(app: AppContext, check_relay: bool) -> None:
    """Show backend, credential-presence, and relay status."""
    executable = _native_executable(app)
    try:
        _, commands = native_command_inventory(executable)
    except RuntimeError as exc:
        _fail(app, str(exc), exit_code=4)
        return
    effective_relay = app.relay_url or NATIVE_DEFAULT_RELAY
    data: dict[str, Any] = {
        "ok": True,
        "backend": "buzz",
        "executable": executable,
        "native_command_count": len(commands),
        "relay_url": effective_relay,
        "native_format": app.output_format,
        "private_key_configured": bool(os.environ.get("BUZZ_PRIVATE_KEY")),
        "auth_tag_configured": bool(os.environ.get("BUZZ_AUTH_TAG")),
        "session_path": str(app.session_store.path),
    }
    if check_relay:
        data["relay"] = check_relay_liveness(effective_relay)
    _emit_value(app, data)


@backend_group.command("commands")
@click.pass_obj
def backend_commands(app: AppContext) -> None:
    """List native root commands and compare wrapper coverage."""
    executable = _native_executable(app)
    try:
        _, native = native_command_inventory(executable)
    except RuntimeError as exc:
        _fail(app, str(exc), exit_code=4)
        return
    wrapped = list(NATIVE_GROUPS)
    data = {
        "ok": True,
        "backend": "buzz",
        "executable": executable,
        "native": native,
        "wrapped": wrapped,
        "missing_from_wrapper": sorted(set(native) - set(wrapped)),
        "not_in_native": sorted(set(wrapped) - set(native)),
    }
    _emit_value(app, data)


@backend_group.command(
    "help",
    context_settings=PROXY_CONTEXT,
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def backend_help(app: AppContext, args: tuple[str, ...]) -> None:
    """Show native Buzz help; optionally name a group or subcommand."""
    native_args: list[str] = []
    if app.relay_url:
        native_args.extend(["--relay", app.relay_url])
    native_args.extend(["--format", app.output_format])
    native_args.extend(args)
    native_args.append("--help")
    _run_native_args(app, native_args)


@cli.group("session")
def session_group() -> None:
    """Manage local, non-secret relay preferences."""


def _session_data(app: AppContext) -> dict[str, Any]:
    return {
        "ok": True,
        "session_path": str(app.session_store.path),
        "saved": app.state.snapshot(),
        "effective": {
            "relay_url": app.relay_url or NATIVE_DEFAULT_RELAY,
            "output_format": app.output_format,
        },
        "undo_depth": len(app.state.history),
        "redo_depth": len(app.state.future),
        "stores_credentials": False,
    }


@session_group.command("status")
@click.pass_obj
def session_status(app: AppContext) -> None:
    """Show saved and effective local configuration."""
    _emit_value(app, _session_data(app))


def _save_or_plan(app: AppContext, action: str) -> None:
    if app.dry_run:
        data = {
            "ok": True,
            "dry_run": True,
            "executed": False,
            "action": action,
            "proposed": app.state.snapshot(),
            "session_path": str(app.session_store.path),
        }
        _emit_value(app, data, human=f"Would {action}: {app.state.snapshot()}")
        return
    app.session_store.save(app.state)
    data = _session_data(app)
    data["action"] = action
    _emit_value(app, data)


@session_group.command("set-relay")
@click.argument("relay_url")
@click.pass_obj
def session_set_relay(app: AppContext, relay_url: str) -> None:
    """Save a relay URL without storing credentials."""
    try:
        relay_url = validate_relay_url(relay_url)
        app.session_store.mutate(app.state, relay_url=relay_url)
    except ValueError as exc:
        _fail(app, str(exc))
        return
    app.relay_url = relay_url
    _save_or_plan(app, "set relay")


@session_group.command("set-format")
@click.argument("output_format", type=click.Choice(["json", "compact"]))
@click.pass_obj
def session_set_format(app: AppContext, output_format: str) -> None:
    """Save the native Buzz read format."""
    app.session_store.mutate(app.state, output_format=output_format)
    app.output_format = output_format
    _save_or_plan(app, "set format")


@session_group.command("undo")
@click.pass_obj
def session_undo(app: AppContext) -> None:
    """Undo the last local preference change."""
    try:
        app.session_store.undo(app.state)
    except ValueError as exc:
        _fail(app, str(exc))
        return
    app.relay_url, app.output_format = resolve_settings(None, None, app.state)
    _save_or_plan(app, "undo local session change")


@session_group.command("redo")
@click.pass_obj
def session_redo(app: AppContext) -> None:
    """Redo the last undone local preference change."""
    try:
        app.session_store.redo(app.state)
    except ValueError as exc:
        _fail(app, str(exc))
        return
    app.relay_url, app.output_format = resolve_settings(None, None, app.state)
    _save_or_plan(app, "redo local session change")


@session_group.command("reset")
@click.pass_obj
def session_reset(app: AppContext) -> None:
    """Reset saved relay and format preferences."""
    app.session_store.reset(app.state)
    app.relay_url, app.output_format = resolve_settings(None, None, app.state)
    _save_or_plan(app, "reset local session")


@session_group.command("path")
@click.pass_obj
def session_path(app: AppContext) -> None:
    """Print the local session path."""
    data = {"ok": True, "session_path": str(app.session_store.path)}
    _emit_value(app, data, human=str(app.session_store.path))


@cli.command(
    "raw",
    context_settings=PROXY_CONTEXT,
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def raw(app: AppContext, args: tuple[str, ...]) -> None:
    """Forward an arbitrary future-compatible native Buzz command."""
    if not args:
        _fail(app, "raw requires a native Buzz command")
        return
    _run_native_group(app, args[0], args[1:])


def _make_proxy(group: str) -> click.Command:
    @click.command(
        name=group,
        help=GROUP_HELP[group],
        context_settings=PROXY_CONTEXT,
        add_help_option=False,
    )
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    @click.pass_obj
    def proxy(app: AppContext, args: tuple[str, ...]) -> None:
        _run_native_group(app, group, args)

    return proxy


for _group in NATIVE_GROUPS:
    cli.add_command(_make_proxy(_group))


@cli.command("repl")
@click.pass_obj
def repl(app: AppContext) -> None:
    """Start the interactive CLI-Anything Buzz shell."""
    history_path = app.session_store.path.parent / "history"
    skin = ReplSkin("buzz", version=__version__, history_file=str(history_path))
    skin.print_banner()
    skin.info("Credentials stay in BUZZ_PRIVATE_KEY and BUZZ_AUTH_TAG.")
    prompt_session = skin.create_prompt_session()
    base_args = ["--session", str(app.session_store.path)]
    if app.use_json:
        base_args.append("--json")
    if app.relay_url:
        base_args.extend(["--relay", app.relay_url])
    base_args.extend(["--format", app.output_format])
    if app.dry_run:
        base_args.append("--dry-run")
    if app.buzz_binary:
        base_args.extend(["--buzz-binary", app.buzz_binary])
    while True:
        try:
            line = skin.get_input(
                prompt_session,
                context=app.relay_url or NATIVE_DEFAULT_RELAY,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            skin.print_goodbye()
            return
        if not line:
            continue
        if line.lower() in {"quit", "exit", "q"}:
            skin.print_goodbye()
            return
        if line.lower() == "help":
            skin.help(
                {
                    "backend": "Inspect the real Buzz executable and relay",
                    "session": "Manage non-secret relay preferences",
                    "<domain>": "Forward any native Buzz domain command",
                    "raw": "Forward a future native command",
                    "quit": "Exit the REPL",
                }
            )
            continue
        try:
            tokens = shlex.split(line)
            cli.main(
                args=[*base_args, *tokens],
                prog_name="cli-anything-buzz",
                standalone_mode=False,
            )
        except ValueError as exc:
            skin.error(f"Parse error: {exc}")
        except click.ClickException as exc:
            skin.error(exc.format_message())
        except click.exceptions.Exit as exc:
            if exc.exit_code:
                skin.error(f"Command exited with status {exc.exit_code}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
