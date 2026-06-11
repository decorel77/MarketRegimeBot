"""QA-003 guard tests: the suite must never touch production artifacts.

The conftest sandbox redirects all artifact writes to pytest's tmp_path;
these tests prove the redirection is active and that a full writing cycle
leaves the real data/system/ directory byte-identical. The session-scoped
``production_artifacts_untouched`` fixture in conftest.py additionally
asserts this across the entire suite run.
"""

from pathlib import Path

from core.regime_classifier import RegimeInput
from tests.conftest import REAL_PROJECT_ROOT, REAL_SYSTEM_DIR, _system_dir_state
from utils import regime_export_writer
from workflow import regime_cycle


def test_sandbox_is_active_and_points_at_tmp(artifact_sandbox):
    assert regime_cycle.PROJECT_ROOT == artifact_sandbox
    assert regime_cycle.RESULT_SNAPSHOT_PATH.is_relative_to(artifact_sandbox)
    assert regime_export_writer.PROJECT_ROOT == artifact_sandbox
    assert regime_export_writer.REGIME_EXPORT_PATH.is_relative_to(artifact_sandbox)
    # And none of them point into the real repo anymore.
    assert not regime_cycle.RESULT_SNAPSHOT_PATH.is_relative_to(REAL_PROJECT_ROOT)
    assert not regime_export_writer.REGIME_EXPORT_PATH.is_relative_to(
        REAL_PROJECT_ROOT
    )


def test_full_writing_cycle_lands_in_sandbox(artifact_sandbox):
    result = regime_cycle.run_regime_cycle(
        write_snapshot=True,
        write_export=True,
        inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
    )
    assert Path(result["result_snapshot_path"]).is_relative_to(artifact_sandbox)
    assert Path(result["regime_export_path"]).is_relative_to(artifact_sandbox)


def test_full_writing_cycle_leaves_production_artifacts_untouched():
    before = _system_dir_state()
    regime_cycle.run_regime_cycle(
        write_snapshot=True,
        write_export=True,
        inputs=RegimeInput(trend_score=0.1, volatility_score=0.2),
    )
    assert _system_dir_state() == before


def test_no_test_artifacts_left_in_production_dir():
    # _test_*.json files were test pollution committed to the repo (QA-003);
    # hermetic tests must never recreate them in the real data/system/.
    leftovers = [p.name for p in REAL_SYSTEM_DIR.glob("_test_*")]
    assert leftovers == []
