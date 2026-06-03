# Releasing a new aurene fork version

This fork (`bursteri/hermes-agent`, branch `aurene-adapter`) is `upstream + a
small set of aurene patches`. When NousResearch cuts a new release tag
(`v2026.X.Y`), follow this runbook to ship a matching fork tag and image.

Watch upstream releases at:
https://github.com/NousResearch/hermes-agent/releases

## Steps

```bash
# 0. Be on aurene-adapter with a clean tree
git switch aurene-adapter
git status   # must be clean

# 1. Fetch the new upstream release tag
git fetch upstream --tags
LATEST=$(git tag --list 'v2026.*' --sort=-v:refname | head -1)
echo "Latest upstream: $LATEST"

git merge-base --is-ancestor "$LATEST" HEAD && \
  { echo "Already on $LATEST — nothing to do"; return; }

# 2. Show the patches that will be replayed onto the new upstream
OLD_BASE=$(git merge-base HEAD upstream/main)
git log --oneline "$OLD_BASE..HEAD"

# 3. Safety: snapshot the current branch
git branch "aurene-adapter.backup-$(date +%Y%m%d-%H%M%S)"

# 4. Rebase the patches onto the new upstream release
git rebase --onto "$LATEST" "$OLD_BASE"
# Conflicts: resolve, `git add <file>`, `git rebase --continue`.
# Bail entirely:  `git rebase --abort`  (branch unchanged).

# 5. Compute the fork tag from the LITERAL post-rebase pyproject version.
#    Use the full version string verbatim — v0.15.2, NOT v0.152. (The old
#    "v0.${MINOR}${PATCH}" formula produced ugly names like v0.152; dropped.)
VERSION=$(grep -E '^version = ' pyproject.toml | head -1 | sed -E 's/.*"([0-9.]+)".*/\1/')
MAX_N=$(git tag --list "v${VERSION}-aurene.*" | sed -E "s/.*-aurene\.//" | sort -n | tail -1)
FORK_TAG="v${VERSION}-aurene.$((${MAX_N:-0} + 1))"
echo "Will tag: $FORK_TAG  (pyproject $VERSION)"

# 6. Push the rebased branch, then the tag
git push --force-with-lease origin aurene-adapter
git tag "$FORK_TAG"
git push origin "$FORK_TAG"

# 7. MANDATORY cleanup — the moment the tag is pushed, the rebase is durable
#    (the tag + reflog are the real safety net) and the backup is dead weight.
#    INVARIANT: the fork carries ONLY `aurene-adapter` and `main`. Delete every
#    backup/temp branch here, every time, so they never accumulate again.
git branch -D $(git branch --list 'aurene-adapter.backup-*') 2>/dev/null || true
git worktree prune
git branch     # confirm: only aurene-adapter + main remain
```

The tag push triggers `.github/workflows/build.yml`, which builds the image
and pushes it to `ghcr.io/bursteri/hermes-agent:$FORK_TAG` (and `:latest`).

## Tag scheme

| Upstream tag | Upstream `pyproject` | Fork tag         |
| ------------ | -------------------- | ---------------- |
| `v2026.4.3`  | `0.7.0`              | `v0.70-aurene.N` |
| `v2026.4.8`  | `0.8.0`              | `v0.80-aurene.N` |

`N` increments for each fork-side patch on top of the same upstream version.

## Files the aurene patches touch

The Aurene platform now lives entirely in `plugins/platforms/aurene/` (a
bundled platform plugin: `adapter.py` + `__init__.py` + `plugin.yaml`). Its
`register(ctx)` wires everything through upstream's `platform_registry`
(adapter creation, auth env vars, cron delivery, platform hint, setup wizard,
status, toolset), so the platform carries **zero** in-place edits to upstream
core files and will never conflict on rebase.

If a rebase conflicts, it'll be in one of these — everything else is upstream.

- `plugins/platforms/aurene/` *(new files, will never conflict)*
- `.github/workflows/build.yml`, `nix.yml`, `tests.yml`
- Agent identity / branding rebrands + `hermes_cli/_aurene_overrides.py`
- Hindsight integration, `_codex_token_inject.py`, Dockerfile, SOUL.md

## Branch hygiene (invariant)

**The fork carries exactly two branches: `aurene-adapter` and `main`.** Nothing
else — no `aurene-adapter.backup-*`, no `*-migration`, no `claude/*` worktree
branches. Step 7 above deletes the backup as part of every release, so it is
never left behind. If stray branches ever reappear (interrupted rebase,
abandoned worktree, agent leftovers), clear them:

```bash
git branch -D $(git branch --list 'aurene-adapter.backup-*' 'aurene-plugin-*') 2>/dev/null
git worktree prune
git for-each-ref --format='%(refname:short)' refs/heads/claude/ | xargs -r git branch -D
git branch   # must show only: aurene-adapter, main
```
