"""conftest.py — Kattappa test suite root configuration.

Ensures the langsmith pytest plugin (registered globally in the system Python
distribution) does not cause an ImportError that aborts test collection.

The plugin entry point resolves its package from the universal-ai venv which
has an incompatible certifi installation.  We suppress the import error early
by monkey-patching importlib.metadata so that the langsmith entry point is
never returned to pluggy's plugin loader.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DEV_SCRIPTS = _ROOT / "scripts" / "dev"
if str(_DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DEV_SCRIPTS))

from environment_guard import require_verified_environment

require_verified_environment()

# ── Suppress the broken langsmith pytest11 entry-point ──────────────────────
# The entry-point is registered in the system Python 3.13 dist-info directory
# but the actual package files live in a separate venv (universal-ai) that
# uses a certifi version incompatible with the current environment.
# We monkey-patch importlib.metadata.entry_points to hide the offending entry.

try:
    import importlib.metadata as _meta
    _original_entry_points = _meta.entry_points

    def _filtered_entry_points(**kwargs):
        eps = _original_entry_points(**kwargs)
        group = kwargs.get("group", "")
        if group == "pytest11":
            # Filter out any entry point whose value references langsmith
            if hasattr(eps, "__iter__"):
                eps = [ep for ep in eps if "langsmith" not in str(ep.value)]
        return eps

    _meta.entry_points = _filtered_entry_points
except Exception:
    pass  # If patching fails, let pytest handle it naturally
