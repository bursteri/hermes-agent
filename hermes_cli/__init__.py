"""
Hermes CLI - Unified command-line interface for Hermes Agent.

Provides subcommands for:
- hermes chat          - Interactive chat (same as ./hermes)
- hermes gateway       - Run gateway in foreground
- hermes gateway start - Start gateway service
- hermes gateway stop  - Stop gateway service  
- hermes setup         - Interactive setup wizard
- hermes status        - Show status of all components
- hermes cron          - Manage cron jobs
"""

__version__ = "0.11.0"
__release_date__ = "2026.4.23"

# Fork-only: install Aurene runtime overrides (disables manual self-update).
# Imported at the end of package init so upstream additions to this file
# stay above this line and never conflict on rebase.
from hermes_cli import _aurene_overrides  # noqa: F401, E402
