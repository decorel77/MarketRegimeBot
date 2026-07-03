"""Tests for MarketRegimeBot — with an import-time artifact sandbox.

MRB-UNITTEST-GUARD-001: the pytest ``tests/conftest.py`` sandbox does NOT run
under ``python -m unittest discover`` — the documented unsafe runner that has
previously written the real OFF-LIMITS ``data/system/regime_export.json`` and
``result_snapshot.json`` (see docs/SAFE_TEST_GATE.md). Importing this package
redirects the production write targets (which late-bind at call time, QA-003)
to a throwaway temp directory, so a stray unittest run can no longer touch
production artifacts. Under pytest this is a harmless baseline: the autouse
``artifact_sandbox`` fixture re-patches the same attributes per test.
"""

from __future__ import annotations

import atexit
import tempfile
from pathlib import Path

from utils import regime_export_writer as _export_writer
from workflow import regime_cycle as _regime_cycle

_SANDBOX = tempfile.TemporaryDirectory(prefix="mrb_unittest_sandbox_")
atexit.register(_SANDBOX.cleanup)
_SANDBOX_ROOT = Path(_SANDBOX.name)
_SANDBOX_SYSTEM_DIR = _SANDBOX_ROOT / "data" / "system"
_SANDBOX_SYSTEM_DIR.mkdir(parents=True, exist_ok=True)

# Same four attributes the pytest conftest patches; the writers' in-project
# guard compares against the (patched) PROJECT_ROOT, so sandbox writes pass
# while the REAL data/system stays untouched.
_regime_cycle.PROJECT_ROOT = _SANDBOX_ROOT
_regime_cycle.RESULT_SNAPSHOT_PATH = _SANDBOX_SYSTEM_DIR / "result_snapshot.json"
_export_writer.PROJECT_ROOT = _SANDBOX_ROOT
_export_writer.REGIME_EXPORT_PATH = _SANDBOX_SYSTEM_DIR / "regime_export.json"
