"""Fork-only runtime overrides for the Aurene deployment.

This module monkey-patches a small set of upstream functions to disable
the manual self-update flow, since aurene-managed instances receive
updates automatically via the Docker image.

Living entirely in this fork-only file means upstream rebases never
have to touch the code that disables updates — the only upstream file
modified by this fork is `hermes_cli/__init__.py`, which imports this
module at the very end of package init.

If upstream removes or renames `check_for_updates` / `cmd_update`, the
patches below silently no-op (we look up the attributes defensively),
so a renamed-but-still-present manual update flow will not break the
import chain — it will just leak through until this file is updated.
"""

from __future__ import annotations


def _check_for_updates_disabled():
    """Replacement for hermes_cli.banner.check_for_updates."""
    return None


def _cmd_update_disabled(args):
    """Replacement for hermes_cli.main.cmd_update."""
    print("Updates are handled automatically — no action needed.")
    print("If you're experiencing issues, please contact support.")
    return None


def apply() -> None:
    """Install the fork-only overrides on top of the imported modules."""
    try:
        from hermes_cli import banner
    except Exception:
        banner = None
    if banner is not None and hasattr(banner, "check_for_updates"):
        banner.check_for_updates = _check_for_updates_disabled

    try:
        from hermes_cli import main as _main
    except Exception:
        _main = None
    if _main is not None and hasattr(_main, "cmd_update"):
        _main.cmd_update = _cmd_update_disabled


apply()
