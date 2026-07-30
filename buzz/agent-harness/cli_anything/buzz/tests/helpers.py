from __future__ import annotations

import json
from pathlib import Path


def make_persona_pack(root: Path, *, valid: bool = True) -> Path:
    pack = root / "synthetic-buzz-pack"
    (pack / ".plugin").mkdir(parents=True)
    (pack / "agents").mkdir()
    manifest = {
        "$schema": "https://open-plugin-spec.org/schema/v1/plugin.json",
        "id": "com.example.cli-anything-buzz-test",
        "name": "CLI Anything Buzz Test",
        "version": "1.2.3",
        "description": "Synthetic public test fixture.",
        "personas": ["agents/test-agent.persona.md"] if valid else [],
        "defaults": {
            "model": "test:synthetic-model",
            "temperature": 0.2,
            "triggers": {
                "mentions": True,
                "keywords": [],
                "all_messages": False,
            },
        },
    }
    (pack / ".plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (pack / "agents" / "test-agent.persona.md").write_text(
        """---
name: test-agent
display_name: "Test Agent"
description: "Synthetic persona for CLI-Anything Buzz tests."
subscribe:
  - "#testing"
triggers:
  mentions: true
---

You are a deterministic synthetic test agent.
""",
        encoding="utf-8",
    )
    return pack
