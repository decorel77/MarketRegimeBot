# MarketRegimeBot — safe test gate & push-readiness (2026-06-28)

Status: **SAFE / docs-only.** Documents the correct broker-free test gate for this
repo and the two OFF-LIMITS blockers that keep it **not push-ready** without a
human decision. No OFF-LIMITS runtime file was read, written, or staged to produce
this note (only metadata `stat` + git tree status). No push.

## Why MarketRegimeBot needs its OWN pandas gate (not `python -S … discover`)

Unlike the pure-stdlib repos, MarketRegimeBot's production code and tests depend on
**pandas / numpy / yfinance(mocked)**. The agreed ecosystem gate
`python -S -m unittest discover` is therefore **wrong for this repo** for two
reasons:

1. **`-S` drops site-packages → 12 `No module named 'pandas'` errors.** These are a
   non-accepted artifact class (only `No module named 'pytest'` is accepted). The
   gate cannot validate this repo broker-free under `-S`.
2. **`unittest discover` bypasses `tests/conftest.py` → it WRITES OFF-LIMITS files.**
   The repo's hermetic sandbox lives in `conftest.py`, which is **pytest-only**.
   Running under plain `unittest` skips it, so the production exporter writes the
   real `data/system/regime_export.json` (and `_test_regime_export.json`). Confirmed:
   a prior `discover` run advanced both files' mtimes.

### The correct gate: pytest in the repo-local broker-free `.venv`

`MarketRegimeBot/.venv` has `pandas`, `numpy`, `pytest`, `yfinance` — and **no
`ib_insync`** (broker-free; verified). `tests/conftest.py` provides:
- `artifact_sandbox` (autouse): monkeypatches `regime_cycle.PROJECT_ROOT` /
  `RESULT_SNAPSHOT_PATH` and `regime_export_writer.PROJECT_ROOT` /
  `REGIME_EXPORT_PATH` into pytest `tmp_path`, so **every** artifact write (incl.
  the `_test_regime_export.json` writer, via the in-project path guard) goes to a
  per-test temp dir.
- `production_artifacts_untouched` (session, autouse): hashes `data/system/`
  before/after the whole run and **asserts byte-identical** — a built-in OFF-LIMITS
  guard.

All `yfinance` use in tests is an **injected mock** (`_make_mock_download`, "no live
yfinance calls"); the reader takes `_download_fn=…`. So the suite performs **no
real fetch and no broker import**.

**Command:**
```
.venv/Scripts/python.exe -m pytest tests/ -q
```

### Gate result (2026-06-28, broker-free `.venv` pytest)

| | |
|---|---|
| passed | **525** (+417 subtests) |
| failed | **1** — `test_artifact_hermeticity.py::test_no_test_artifacts_left_in_production_dir` |
| OFF-LIMITS `regime_export.json` mtime/size | **UNCHANGED** (`1782635067` / 534 before == after) |
| OFF-LIMITS `_test_regime_export.json` mtime/size | **UNCHANGED** (`1782635066` / 514 before == after) |

The sandbox works (real artifacts untouched). Old gate vs new gate:
`python -S discover` = 18 errors (6 pytest + 12 pandas) **and writes OFF-LIMITS**;
`.venv pytest` = 525 pass, OFF-LIMITS untouched, 1 hermeticity failure (below).

## Blockers preventing a clean, push-ready GREEN (need human decision)

### Blocker 1 — leftover pollution file fails the hermeticity guard
`data/system/_test_regime_export.json` exists in the working tree (untracked `??`)
as **test pollution** left by earlier *wrong* `unittest discover` runs. The repo's
own `test_no_test_artifacts_left_in_production_dir` asserts no `_test_*` file exists
under the real `data/system/` and therefore **fails**. This is not a code
regression. To go green the pollution file must be **removed** — but it lives under
the OFF-LIMITS `data/system/` dir, so it is **not** deleted here without approval.

### Blocker 2 — the OFF-LIMITS runtime file `regime_export.json` is git-TRACKED and modified in the +22 commits
`regime_export.json` is **tracked** at both `origin/main` and `HEAD` (a pre-existing
repo-hygiene issue: a runtime artifact committed into git). Commit
`017cb36 fix(QA-003): isolate regime tests from production artifacts` (one of the 22
unpushed commits) **modifies** the tracked `regime_export.json` (M) and **removes**
`_test_regime_export.json` from tracking (D). Pushing would therefore **publish a
committed snapshot of OFF-LIMITS runtime data**. This needs a human decision; the
clean fix is to `git rm --cached data/system/regime_export.json` + gitignore it
(as was done for `_test_regime_export.json`), which rewrites OFF-LIMITS tracking and
is itself HUMAN_GATED.

## Disposition

MarketRegimeBot is **NOT pushed**. The broker-free `.venv` pytest gate is the
correct convention (documented above) and proves the sandbox keeps the real
artifacts untouched — but a push is gated on two human decisions: (1) remove the
`_test_regime_export.json` pollution file, and (2) decide how to handle the tracked
`regime_export.json` runtime artifact in the committed history. No gate was widened,
no dependency installed, no OFF-LIMITS file read/written/staged, no push.
