from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cli_anything.buzz.core.commands import NATIVE_GROUPS, build_native_args
from cli_anything.buzz.tests.helpers import make_persona_pack
from cli_anything.buzz.utils.buzz_backend import native_command_inventory, run_buzz


def _resolve_cli(name: str) -> list[str]:
    """Resolve installed CLI command; fall back to python -m for development."""
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = name.replace("cli-anything-", "cli_anything.")
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


def test_real_backend_root_inventory_matches_wrapper() -> None:
    executable, commands = native_command_inventory()
    assert Path(executable).is_file()
    assert commands == list(NATIVE_GROUPS)
    print(f"\n  Buzz executable: {executable}")
    print(f"  Native command groups: {len(commands)}")


def test_real_backend_validates_synthetic_persona_pack(tmp_path: Path) -> None:
    pack = make_persona_pack(tmp_path)
    result = run_buzz(
        build_native_args(
            "pack", ["validate", str(pack)], relay_url=None, output_format="json"
        )
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Valid."
    print(f"\n  Validated persona pack: {pack}")


def test_real_backend_inspects_resolved_persona_pack(tmp_path: Path) -> None:
    pack = make_persona_pack(tmp_path)
    result = run_buzz(
        build_native_args(
            "pack", ["inspect", str(pack)], relay_url=None, output_format="json"
        )
    )
    assert result.returncode == 0, result.stderr
    assert "Pack: CLI Anything Buzz Test" in result.stdout
    assert "Version: 1.2.3" in result.stdout
    assert "Personas: 1" in result.stdout
    assert "test-agent" in result.stdout
    print(f"\n  Inspected persona pack: {pack}")


def test_real_backend_rejects_invalid_persona_pack(tmp_path: Path) -> None:
    pack = make_persona_pack(tmp_path, valid=False)
    result = run_buzz(
        build_native_args(
            "pack", ["validate", str(pack)], relay_url=None, output_format="json"
        )
    )
    assert result.returncode == 1
    error = json.loads(result.stderr.splitlines()[-1])
    assert error["error"] == "user_error"
    assert "Validation failed" in error["message"]


class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-buzz")

    def _run(
        self,
        args: list[str],
        *,
        check: bool = True,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self.CLI_BASE, *args],
            capture_output=True,
            text=True,
            check=check,
            env=env,
            input=input_text,
        )

    @staticmethod
    def _fake_buzz(tmp_path: Path, body: str = 'printf "%s\\n" "$*"') -> Path:
        script = tmp_path / "buzz"
        script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        script.chmod(0o755)
        return script

    def test_installed_cli_help_lists_all_domains(self) -> None:
        result = self._run(["--help"])
        for group in NATIVE_GROUPS:
            assert group in result.stdout
        assert "backend" in result.stdout
        assert "session" in result.stdout

    def test_installed_cli_backend_status_is_secret_safe(self, tmp_path: Path) -> None:
        session = tmp_path / "session.json"
        result = self._run(["--session", str(session), "--json", "backend", "status"])
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert Path(data["executable"]).is_file()
        assert data["native_command_count"] == 21
        assert isinstance(data["private_key_configured"], bool)
        assert "BUZZ_PRIVATE_KEY" not in result.stdout

    def test_installed_cli_session_round_trip_undo_and_redo(
        self,
        tmp_path: Path,
    ) -> None:
        session = tmp_path / "session.json"
        prefix = ["--session", str(session), "--json"]
        self._run([*prefix, "session", "set-relay", "https://relay.example.com"])
        self._run([*prefix, "session", "set-format", "compact"])
        undone = json.loads(self._run([*prefix, "session", "undo"]).stdout)
        assert undone["saved"]["output_format"] == "json"
        redone = json.loads(self._run([*prefix, "session", "redo"]).stdout)
        assert redone["saved"]["output_format"] == "compact"
        reloaded = json.loads(self._run([*prefix, "session", "status"]).stdout)
        assert reloaded["saved"]["relay_url"] == "https://relay.example.com"
        assert reloaded["saved"]["output_format"] == "compact"

    def test_installed_cli_session_reset(self, tmp_path: Path) -> None:
        session = tmp_path / "session.json"
        prefix = ["--session", str(session), "--json"]
        self._run([*prefix, "session", "set-format", "compact"])
        reset = json.loads(self._run([*prefix, "session", "reset"]).stdout)
        assert reset["saved"] == {"relay_url": None, "output_format": "json"}

    def test_concurrent_session_updates_are_not_lost(self, tmp_path: Path) -> None:
        session = tmp_path / "session.json"
        session_args = ["--session", str(session), "--json", "session"]
        prefix = [*self.CLI_BASE, *session_args]
        processes = [
            subprocess.Popen(
                [*prefix, "set-relay", "https://relay.example.com"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
            subprocess.Popen(
                [*prefix, "set-format", "compact"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
        ]
        for process in processes:
            _, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stderr
        saved = json.loads(self._run([*session_args, "status"]).stdout)
        assert saved["saved"] == {
            "relay_url": "https://relay.example.com",
            "output_format": "compact",
        }
        assert saved["undo_depth"] == 2

    def test_installed_cli_dry_run_does_not_contact_relay(
        self,
        tmp_path: Path,
    ) -> None:
        session = tmp_path / "session.json"
        result = self._run(
            [
                "--session",
                str(session),
                "--relay",
                "https://unreachable.invalid",
                "--dry-run",
                "--json",
                "messages",
                "send",
                "--channel",
                "00000000-0000-0000-0000-000000000000",
                "--content",
                "Synthetic message",
            ]
        )
        data = json.loads(result.stdout)
        assert data["executed"] is False
        assert data["dry_run"] is True
        assert "https://unreachable.invalid" in data["command"]

    def test_installed_cli_forwards_pack_validate(self, tmp_path: Path) -> None:
        pack = make_persona_pack(tmp_path)
        result = self._run(["--json", "pack", "validate", str(pack)])
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["backend"] == "buzz"
        assert data["data"] == "Valid."
        print(f"\n  CLI validated persona pack: {pack}")

    def test_installed_cli_forwards_pack_inspect(self, tmp_path: Path) -> None:
        pack = make_persona_pack(tmp_path)
        result = self._run(["--json", "pack", "inspect", str(pack)])
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert "Pack: CLI Anything Buzz Test" in data["data"]
        assert "Personas: 1" in data["data"]
        print(f"\n  CLI inspected persona pack: {pack}")

    def test_installed_cli_rejects_private_key_argument(self) -> None:
        result = self._run(
            ["--json", "messages", "get", "--private-key", "nsec_test_secret"],
            check=False,
        )
        assert result.returncode == 1
        assert "nsec_test_secret" not in result.stdout
        assert "nsec_test_secret" not in result.stderr
        data = json.loads(result.stderr)
        assert "BUZZ_PRIVATE_KEY" in data["error"]["message"]

    def test_installed_cli_rejects_auth_tag_argument(self) -> None:
        result = self._run(
            ["--json", "channels", "list", "--auth-tag=synthetic-secret"],
            check=False,
        )
        assert result.returncode == 1
        assert "synthetic-secret" not in result.stdout
        assert "synthetic-secret" not in result.stderr
        data = json.loads(result.stderr)
        assert "BUZZ_AUTH_TAG" in data["error"]["message"]

    def test_usage_error_is_structured_json_with_input_exit_code(self) -> None:
        result = self._run(["--json", "--unknown-option"], check=False)
        assert result.returncode == 1
        data = json.loads(result.stderr)
        assert data["ok"] is False
        assert data["exit_code"] == 1
        assert "No such option" in data["error"]["message"]

    def test_native_timeout_is_structured_json(self, tmp_path: Path) -> None:
        script = self._fake_buzz(tmp_path, "sleep 2")
        result = self._run(
            [
                "--json",
                "--buzz-binary",
                str(script),
                "--timeout",
                "0.01",
                "raw",
                "messages",
                "get",
            ],
            check=False,
        )
        assert result.returncode == 4
        data = json.loads(result.stderr)
        assert data["exit_code"] == 4
        assert "timed out" in data["error"]["message"]

    def test_raw_and_backend_help_forward_unchanged(self, tmp_path: Path) -> None:
        script = self._fake_buzz(tmp_path)
        common = ["--buzz-binary", str(script)]
        raw = self._run([*common, "raw", "future-group", "--flag", "value"])
        assert "future-group --flag value" in raw.stdout
        help_result = self._run([*common, "backend", "help", "messages"])
        assert "messages --help" in help_result.stdout

    def test_default_repl_handles_global_only_and_refreshes_session(
        self, tmp_path: Path
    ) -> None:
        script = self._fake_buzz(tmp_path)
        session = tmp_path / "session.json"
        result = self._run(
            ["--session", str(session), "--buzz-binary", str(script)],
            input_text=(
                "--json\nrepl\nsession set-format compact\nraw messages get\nquit\n"
            ),
        )
        combined = result.stdout + result.stderr
        assert "global options" in combined
        assert "cannot be opened from inside itself" in combined
        assert combined.count("cli-anything · Buzz") == 1
        assert "--format compact messages get" in combined

    def test_session_write_failure_is_structured_json(self, tmp_path: Path) -> None:
        not_directory = tmp_path / "not-a-directory"
        not_directory.write_text("block", encoding="utf-8")
        result = self._run(
            [
                "--json",
                "--session",
                str(not_directory / "session.json"),
                "session",
                "set-format",
                "compact",
            ],
            check=False,
        )
        assert result.returncode == 1
        data = json.loads(result.stderr)
        assert data["ok"] is False
        assert data["error"]["error"] == "wrapper_error"

    def test_raw_rejects_url_embedded_credentials(self) -> None:
        result = self._run(
            [
                "--json",
                "--dry-run",
                "raw",
                "messages",
                "get",
                "--relay",
                "https://user:secret@relay.example.com",
            ],
            check=False,
        )
        assert result.returncode == 1
        assert "secret" not in result.stderr
