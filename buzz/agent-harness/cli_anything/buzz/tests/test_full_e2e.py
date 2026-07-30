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
    result = run_buzz(build_native_args("pack", ["validate", str(pack)], relay_url=None, output_format="json"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Valid."
    print(f"\n  Validated persona pack: {pack}")


def test_real_backend_inspects_resolved_persona_pack(tmp_path: Path) -> None:
    pack = make_persona_pack(tmp_path)
    result = run_buzz(build_native_args("pack", ["inspect", str(pack)], relay_url=None, output_format="json"))
    assert result.returncode == 0, result.stderr
    assert "Pack: CLI Anything Buzz Test" in result.stdout
    assert "Version: 1.2.3" in result.stdout
    assert "Personas: 1" in result.stdout
    assert "test-agent" in result.stdout
    print(f"\n  Inspected persona pack: {pack}")


def test_real_backend_rejects_invalid_persona_pack(tmp_path: Path) -> None:
    pack = make_persona_pack(tmp_path, valid=False)
    result = run_buzz(build_native_args("pack", ["validate", str(pack)], relay_url=None, output_format="json"))
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
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self.CLI_BASE, *args],
            capture_output=True,
            text=True,
            check=check,
        )

    def test_installed_cli_help_lists_all_domains(self) -> None:
        result = self._run(["--help"])
        for group in NATIVE_GROUPS:
            assert group in result.stdout
        assert "backend" in result.stdout
        assert "session" in result.stdout

    def test_installed_cli_backend_status_is_secret_safe(self, tmp_path: Path) -> None:
        session = tmp_path / "session.json"
        result = self._run(
            ["--session", str(session), "--json", "backend", "status"]
        )
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
