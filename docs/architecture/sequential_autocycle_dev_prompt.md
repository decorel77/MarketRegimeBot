# MarketRegimeBot — Sequential Autocycle Developer Prompt Template

## What this file is

A reusable prompt template for future Claude autocycle runs on this repository.
Copy and paste the prompt in the **Prompt** section below when starting a new
autocycle session. Fill in the bracketed placeholders before sending.

This file is **documentation only**. No autocycle execution logic lives here.

---

## When to use an autocycle run

Use this template when:
- One or more `"autocycle_eligible": true` tasks exist in `data/system/task_queue.json`
- The human operator is available to review, approve, commit, and push at the end
- All validators and tests pass on the current branch before starting

Do NOT use this template if:
- The next TODO task is `"autocycle_eligible": false`
- Tests are failing
- There are uncommitted changes on the branch

---

## How to determine eligible tasks

Before starting, inspect `data/system/task_queue.json`:

```
Tasks eligible for autocycle:
  status == "TODO"
  autocycle_eligible == true  (or task_type in ["DOCS", "SCHEMA", "TEST", "DOCS_SCHEMA"])
  risk == "LOW"
```

The lowest-numbered eligible task is always taken first.

---

## Prompt

---

**AUTOCYCLE RUN — MarketRegimeBot**

Repository: `C:\NovaGPT\Apps\MarketRegimeBot`

**RULES (read before starting)**

1. Start with the lowest-numbered `TODO` task in `data/system/task_queue.json`.
   Do not cherry-pick easier or later tasks. Do not skip ahead.

2. Complete up to **2 tasks** per run. Stop after 2 whether or not there are
   more eligible tasks remaining.

3. Only work on tasks where `autocycle_eligible == true` OR `task_type` is one
   of: `DOCS`, `SCHEMA`, `TEST`, `DOCS_SCHEMA`. Stop immediately if the next
   task is `CODE`, `BROKER`, `EXECUTION`, or any forbidden type.

4. If a task is too large to complete safely in one pass, split it:
   - Rename the original task `TASK-XXXA` in `task_queue.json` (documentation /
     schema / test portion).
   - Create `TASK-XXXB` (implementation portion, `autocycle_eligible: false`).
   - Complete `TASK-XXXA` immediately in this run.
   - Leave `TASK-XXXB` as TODO for a future human-reviewed session.

5. After completing each task, run all tests:
   ```
   python -m unittest discover tests
   python -m utils.regime_registry_validator
   python -m utils.autocycle_policy_validator
   ```
   If any test fails, stop the run and report the failure. Do not proceed to the
   next task.

6. **No commit without explicit human approval.** At the end of the run, present
   the full diff and proposed commit message. Wait for the human to confirm
   before committing.

7. **No push without explicit human approval.** After committing, present the
   commit hash and proposed push command. Wait for the human to confirm.

8. Stop immediately and report if any of the following would be required:
   - Broker API access
   - Order placement or routing
   - TWS / IBKR connections
   - Live market data calls
   - `.env` or credential file access
   - Capital allocation or sizing
   - Telegram execution commands
   - Scheduler job creation
   - Background workers or autonomous loops
   - Writes to sibling NOVA repositories

**TASK TO COMPLETE**

Next eligible task: `[REGIME-PHASE-XXX]` — `[task title]`

Read the task description from `data/system/task_queue.json` and complete it.

**DELIVERABLE**

Return at the end of the run:

1. Tasks completed (IDs and titles)
2. Files created or modified
3. Test results (exact output)
4. Validator output
5. Proposed commit message
6. Git diff summary
7. Safety review (confirm no forbidden changes)
8. Request for human approval to commit

---

## Forbidden actions checklist

Before considering a run complete, verify none of the following occurred:

| Check | Required result |
|---|---|
| Broker code modified | NO |
| Trading logic modified | NO |
| Scheduler created | NO |
| Telegram runtime modified | NO |
| TWS/IBKR code touched | NO |
| `.env` or credentials touched | NO |
| Order routing added | NO |
| Capital allocation added | NO |
| Background worker created | NO |
| Autonomous commit executed | NO |
| Autonomous push executed | NO |
| Writes to sibling NOVA repos | NO |
| `execution_allowed` set to true | NO |
| `enabled` (autocycle policy) set to true | NO |

---

## Safety fields to verify at every run end

Read `data/system/autocycle_policy.json` and confirm:

```json
"execution_allowed": false
"enabled": false
"runtime_effect": false
"commit_requires_human_approval": true
"push_requires_human_approval": true
"allowed_risk_levels": ["LOW"]
```

If any of these are not as specified above, the run has a safety violation and
must be reported immediately without committing.

---

## Example autocycle-eligible tasks

Tasks that are safe for autocycle:

| Type | Example |
|---|---|
| `DOCS` | Create or update a `.md` documentation file |
| `SCHEMA` | Expand or update a `.json` schema file |
| `TEST` | Add unit tests for inert policy/registry fields |
| `DOCS_SCHEMA` | Combined documentation + schema definition task |

Tasks that are **NOT** safe for autocycle:

| Type | Example |
|---|---|
| `CODE` | Implement a data reader, classifier, or adapter |
| `BROKER` | Any task touching broker integration |
| `EXECUTION` | Any task enabling trading or order logic |

---

## Version history

| Date | Change |
|---|---|
| 2026-06-07 | Initial template created |
