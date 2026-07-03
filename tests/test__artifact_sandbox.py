"""Pin the unittest artifact sandbox (MRB-UNITTEST-GUARD-001).

``python -m unittest discover`` bypasses the pytest conftest sandbox and has
previously written the real OFF-LIMITS regime_export.json/result_snapshot.json
(docs/SAFE_TEST_GATE.md). These tests fail loudly if the redirect ever stops
protecting the production artifacts — under pytest the autouse fixture, under
unittest the tests/__init__.py package sandbox.
"""

from __future__ import annotations

import unittest
from pathlib import Path

# Safety net for TOP-LEVEL discovery mode (`discover -s tests` without
# `-t .`), where test modules import as top-level modules and the package
# __init__ would otherwise never run. This module's double-underscore name
# sorts FIRST, so the sandbox activates before any other test module loads.
import tests  # noqa: F401  (side effect: activates the artifact sandbox)

from utils import regime_export_writer
from workflow import regime_cycle

_REAL_ROOT = Path(__file__).resolve().parents[1]
_REAL_SNAPSHOT = (_REAL_ROOT / "data" / "system" / "result_snapshot.json").resolve()
_REAL_EXPORT = (_REAL_ROOT / "data" / "system" / "regime_export.json").resolve()


class ArtifactSandboxTests(unittest.TestCase):
    def test_result_snapshot_target_is_not_the_real_file(self):
        self.assertNotEqual(
            Path(regime_cycle.RESULT_SNAPSHOT_PATH).resolve(),
            _REAL_SNAPSHOT,
            "artifact sandbox inactive: result snapshot would hit production",
        )

    def test_regime_export_target_is_not_the_real_file(self):
        self.assertNotEqual(
            Path(regime_export_writer.REGIME_EXPORT_PATH).resolve(),
            _REAL_EXPORT,
            "artifact sandbox inactive: regime export would hit production",
        )

    def test_write_guard_root_moved_with_the_sandbox(self):
        # The writers refuse paths outside PROJECT_ROOT; with the sandbox
        # active that guard root must not be the real repo anymore.
        self.assertNotEqual(Path(regime_cycle.PROJECT_ROOT).resolve(), _REAL_ROOT)
        self.assertNotEqual(Path(regime_export_writer.PROJECT_ROOT).resolve(), _REAL_ROOT)


if __name__ == "__main__":
    unittest.main()
