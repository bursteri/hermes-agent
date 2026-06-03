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

# 5. Compute the fork tag name from the post-rebase pyproject version
VERSION=$(grep -E '^version = ' pyproject.toml | head -1 | sed -E 's/.*"([0-9.]+)".*/\1/')
MINOR=$(echo "$VERSION" | cut -d. -f2)
PATCH=$(echo "$VERSION" | cut -d. -f3)
TAG_BASE="v0.${MINOR}${PATCH}"
MAX_N=$(git tag --list "${TAG_BASE}-aurene.*" | sed -E "s/.*-aurene\.//" | sort -n | tail -1)
FORK_TAG="${TAG_BASE}-aurene.$((${MAX_N:-0} + 1))"
echo "Will tag: $FORK_TAG  (pyproject $VERSION)"

# 6. Push the rebased branch, then the tag
git push --force-with-lease origin aurene-adapter
git tag "$FORK_TAG"
git push origin "$FORK_TAG"
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

## Cleanup

Once the new image is verified, drop the backup branches:

```bash
git branch -D $(git branch --list 'aurene-adapter.backup-*')
```
