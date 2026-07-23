# Personal Fork Policy

This repository is the public GitHub fork `kombiz/CLI-Anything` of
[`HKUDS/CLI-Anything`](https://github.com/HKUDS/CLI-Anything).

The fork exists to keep receiving upstream improvements while supporting
Kombiz-owned CLI harnesses. Fork ownership does not transfer authorship or
ownership of upstream code.

## Public repository warning

This fork is public. Treat every tracked file, commit, branch, issue, Actions
log, and pull request as public information.

Never commit:

- API keys, access tokens, cookies, passwords, or private certificates
- `.env` files other than sanitized `.env.example` or `.env.template` files
- personal documents, user databases, browser profiles, or application state
- private service URLs, customer names, account IDs, or production data
- generated sessions, local caches, recordings, exports, or test artifacts
  containing real user data

Use synthetic fixtures in tests. Put machine-local material under `.local/` or
`private/`; both names are ignored throughout the repository. Before every
commit, inspect `git diff --cached` and run a secret scan if one is available.

## Repository and branch roles

| Name | Role | May contain personal CLI work? |
|---|---|---|
| `upstream` | Read-only remote for `HKUDS/CLI-Anything` | No |
| `origin` | Writable remote for `kombiz/CLI-Anything` | Yes |
| `main` | Clean synchronization branch tracking `upstream/main` | No |
| `personal/main` | Long-lived integration branch for this fork | Yes |
| `personal/<cli-slug>` | Short-lived branch for one personal CLI | Yes |
| `upstream/<topic>` | Short-lived branch intended for an upstream PR | Only the contribution itself |

The local `upstream` push URL is deliberately set to `DISABLED`. This prevents
an accidental direct push to the canonical project.

## Ownership boundary

Treat files in this order:

1. **Upstream-owned:** every file inherited from `HKUDS/CLI-Anything`.
2. **Fork-policy-owned:** `FORK_POLICY.md`, `PERSONAL_CLIS.json`, and the
   `Personal fork safety` block in `.gitignore`.
3. **Personal-CLI-owned:** only paths explicitly listed in
   `PERSONAL_CLIS.json`.

A path not listed as personal is upstream-owned even when it is modified on
`personal/main`. Keep upstream modifications minimal so updates remain easy to
merge. Do not relabel an existing upstream harness as personal.

## Adding a personal CLI

Personal harnesses retain the upstream layout so they can be tested, packaged,
and later proposed upstream without restructuring:

```text
<cli-slug>/
└── agent-harness/
    ├── <SOFTWARE>.md
    ├── setup.py or pyproject.toml
    └── cli_anything/
        └── <python_name>/

skills/
└── cli-anything-<cli-slug>/
    └── SKILL.md
```

For each new CLI:

1. Start from the personal integration branch:

   ```bash
   git switch personal/main
   git switch -c personal/<cli-slug>
   ```

2. Generate the harness from the target software with CLI-Anything. Keep the
   target software checkout separate from this repository, then copy only the
   generated `agent-harness/` into `<cli-slug>/agent-harness/`.
3. Add the new root software directory to the allowlists in `.gitignore`
   Steps 4, 5, and 6. This is required because upstream intentionally ignores
   target application source code and tracks only harnesses.
4. Generate or copy the canonical skill to
   `skills/cli-anything-<cli-slug>/SKILL.md`.
5. Add an entry to `PERSONAL_CLIS.json` before the first commit. This is the
   authoritative ownership inventory for the fork.
6. Use only synthetic test data, review the staged diff, and run the harness
   unit tests. Run E2E tests only against a safe test account or disposable
   local backend.
7. Merge the reviewed branch into `personal/main` and push it to `origin`.

Do not add a fork-only CLI to upstream `registry.json`. Add it there only when
publishing it to CLI-Hub under the upstream contribution rules.

## Synchronizing upstream

Update the clean mirror branch first:

```bash
git switch main
git fetch --prune upstream
git merge --ff-only upstream/main
git push origin main
```

Then merge the refreshed mirror into the personal integration branch:

```bash
git switch personal/main
git merge main
git push origin personal/main
```

Resolve conflicts in favor of current upstream behavior unless a conflict is
inside a path listed in `PERSONAL_CLIS.json` or in the three fork-policy-owned
files above. Record any intentional upstream override in the relevant personal
CLI entry's `notes` field.

## Preparing an upstream contribution

Create a clean branch directly from `upstream/main`, then copy only the CLI
being proposed plus the upstream-required registry and documentation changes:

```bash
git fetch upstream
git switch -c upstream/<cli-slug> upstream/main
```

Do not include `FORK_POLICY.md`, `PERSONAL_CLIS.json`, unrelated personal CLIs,
local configuration, or merge commits from `personal/main` in an upstream pull
request.
