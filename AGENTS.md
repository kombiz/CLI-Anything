# AGENTS.md — kombiz/CLI-Anything fork

This file is the root agent-policy authority for the personal fork. Read
`FORK_POLICY.md` before changing anything; it defines ownership and branch
boundaries that take precedence over ordinary repository conventions.

## Repository identity

This public repository is `kombiz/CLI-Anything`, a personal fork of
`HKUDS/CLI-Anything`. Fork ownership does not transfer ownership of upstream
code. The canonical Greymatter registry has a `CLI-Anything` tools collection,
but its blank GitHub field and `/opt/stacks/CLI-Anything` path do not prove that
this checkout is the same project. Do not copy that identifier into this repo
without an explicit registry reconciliation.

## Branch and ownership rules

- `main` is a clean synchronization branch for `upstream/main`; never land
  fork-only documentation or personal harnesses there.
- `personal/main` is the fork's long-lived integration branch.
- `personal/<cli-slug>` is a reviewed topic branch for one personal harness.
- `upstream/<topic>` begins at `upstream/main` and contains only material meant
  for an upstream pull request.
- The exact fork-policy-owned and personal-CLI-owned paths are listed in
  `FORK_POLICY.md` and `PERSONAL_CLIS.json`. Treat every other path as
  upstream-owned.

Do not push to `upstream`; its push URL is deliberately disabled. Changes for
this fork go to `origin`, and topic branches are reviewed before they merge
into `personal/main`.

## Working safely

This is a public repository. Never commit credentials, private URLs, personal
data, real application state, session artifacts, or sensitive fixtures. Use
synthetic test data and inspect the staged diff before every commit.

For repository-wide validation, use the exact checks selected by the changed
paths:

- root skill mirror: `python3 .github/scripts/validate_root_skills.py`
- Codex installer: `bash codex-skill/tests/test_install.sh`
- PR labeler: `npm test --prefix .github/scripts` only when that package exposes
  the script in the current upstream revision
- a harness: use the commands in its `agent-harness` manifest and test guide

Do not claim the entire multi-harness estate passed when only fork-policy or
Repobook JSON changed. Always run `git diff --check` and parse modified JSON.

## Tasks, credentials, and publishing

`.plan/tasks.json` is the fork-level execution truth. The four `.plan` JSON
files form the repository's Repobook chapter; preserve history and `starred`,
and publish only the exact landed `personal/main` revision.

The upstream Pages workflow consumes DigitalOcean Spaces settings through
GitHub Actions secrets. A `.homelab-secrets.yaml` must contain verified
immutable references and the actual CI trust boundary; do not invent a
project UUID or copy a value. If `secretctl locate` cannot run from an approved
trusted execution context, record the handoff as manual-required.

The landed-revision publisher is `.github/workflows/repobook.yml`. It runs on
`personal/main`, not `main`, because `main` must remain a byte-for-byte-capable
upstream synchronization surface.
