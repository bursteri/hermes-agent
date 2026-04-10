"""Fork-only runtime overrides for the Aurene deployment.

This module monkey-patches upstream modules to rebrand the agent and
disable the manual self-update flow.  All fork-specific behavioral
changes live here so upstream files stay untouched — the only upstream
file modified by this fork is `hermes_cli/__init__.py`, which imports
this module at the very end of package init.

Patches are applied defensively: if upstream renames or removes a
target, the patch silently no-ops.
"""

from __future__ import annotations

# -- Aurene identity ----------------------------------------------------------

_AURENE_SOUL = (
    "You are Aurene Agent, an intelligent AI assistant created by Noste AI. "
    "You are helpful, knowledgeable, and direct. You assist users with a wide "
    "range of tasks including answering questions, writing and editing code, "
    "analyzing information, creative work, and executing actions via your tools. "
    "You communicate clearly, admit uncertainty when appropriate, and prioritize "
    "being genuinely useful over being verbose unless otherwise directed below. "
    "Be targeted and efficient in your exploration and investigations."
)


# -- Update flow disabled -----------------------------------------------------

def _check_for_updates_disabled():
    """Replacement for hermes_cli.banner.check_for_updates."""
    return None


def _cmd_update_disabled(args):
    """Replacement for hermes_cli.main.cmd_update."""
    print("Updates are handled automatically — no action needed.")
    print("If you're experiencing issues, please contact support.")
    return None


# -- SOUL.md migration --------------------------------------------------------

def _migrate_soul_md() -> None:
    """Ensure SOUL.md on disk carries the Aurene identity.

    Overwrites SOUL.md if it exists but doesn't mention "Aurene" (i.e. it
    still has the upstream Hermes default or the empty Docker template).
    Seeds a new file if none exists.  Skips on subsequent runs via a
    sentinel file so we only touch the filesystem once.
    """
    try:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
        sentinel = home / ".aurene_migrated"
        if sentinel.exists():
            return
        soul_path = home / "SOUL.md"
        if soul_path.exists():
            current = soul_path.read_text(encoding="utf-8")
            if "Aurene" not in current:
                soul_path.write_text(_AURENE_SOUL, encoding="utf-8")
        else:
            soul_path.write_text(_AURENE_SOUL, encoding="utf-8")
        sentinel.write_text("1", encoding="utf-8")
    except Exception:
        pass


# -- Apply all overrides ------------------------------------------------------

def apply() -> None:
    """Install the fork-only overrides on top of the imported modules."""

    # 1. Identity: patch DEFAULT_SOUL_MD and DEFAULT_AGENT_IDENTITY
    try:
        from hermes_cli import default_soul
        default_soul.DEFAULT_SOUL_MD = _AURENE_SOUL
    except Exception:
        pass

    try:
        from agent import prompt_builder
        prompt_builder.DEFAULT_AGENT_IDENTITY = _AURENE_SOUL
    except Exception:
        pass

    # 2. Migrate existing SOUL.md on disk
    _migrate_soul_md()

    # 3. Disable manual update flow
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
