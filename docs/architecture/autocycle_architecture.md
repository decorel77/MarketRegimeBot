# Autocycle Architecture — MarketRegimeBot

## Classification

| Property | Value |
|---|---|
| Status | PLANNING ONLY — not implemented |
| Execution | Disabled (`execution_allowed: false`) |
| Autonomous commits | Not permitted |
| Autonomous pushes | Not permitted |
| Human approval | Mandatory before any commit or push |
| Runtime effect | None (`runtime_effect: false`) |

---

## Purpose

The autocycle system is a future capability that will allow MarketRegimeBot to
prepare a small batch of LOW-risk documentation, schema, or test tasks and
present them to a human operator for review and approval before any changes are
committed or pushed.

The autocycle **never acts autonomously**. Its entire role is to select,
prepare, and report — then stop and wait for a human.

---

## Permanent Constraints (All Phases, No Exceptions)

- Maximum 3 LOW-risk tasks selected per cycle
- Human approval is required before any commit
- Human approval is required before any push
- Execution of trading, broker, or order logic is permanently prohibited
- Autocycle cannot modify `.env`, credentials, or broker configuration
- Autocycle cannot trigger Telegram execution commands
- Autocycle cannot connect to TWS, IBKR, or any broker API
- Autocycle cannot allocate capital or influence position sizing

---

## Phase 1 — Read Task Queue

**Purpose:** Load the current task queue from `data/system/task_queue.json`.

**Input:** `data/system/task_queue.json`

**Output:** In-memory list of pending tasks

**Safety:**
- Read-only file operation
- No network access
- No broker access
- No execution

**Implementation note (future):**
```python
# tasks = json.load(open("data/system/task_queue.json"))
# candidate_pool = [t for t in tasks if t["status"] == "TODO"]
```

---

## Phase 2 — Task Classification

**Purpose:** Classify each candidate task by risk level, type, and eligibility
for autocycle execution.

**Classification dimensions:**

| Dimension | Values |
|---|---|
| Risk level | LOW / MEDIUM / HIGH |
| Task type | DOCS / SCHEMA / TEST / CODE / BROKER / EXECUTION |
| Autocycle eligible | true / false |

**Eligibility rules:**
- Risk level must be `LOW`
- Task type must be one of: `DOCS`, `SCHEMA`, `TEST`
- Task type `CODE`, `BROKER`, or `EXECUTION` → always ineligible
- Any task touching broker, trading, or execution logic → always ineligible

**Output:** Annotated task list with `autocycle_eligible` flag per task

**Safety:** Pure classification logic — no side effects, no I/O beyond reading
the already-loaded task list.

---

## Phase 3 — Safety Filter

**Purpose:** Apply a strict safety gate to the classified task list. Any task
that fails a safety check is dropped from the cycle, never queued for execution.

**Safety filter checks (all must pass):**

1. `risk == "LOW"` — task risk is explicitly LOW
2. `autocycle_eligible == true` — task passed classification
3. `task_type not in {"BROKER", "EXECUTION", "CODE"}` — type exclusion
4. Task description contains no keywords: `broker`, `order`, `trade`, `tweak`,
   `IBKR`, `TWS`, `telegram`, `credential`, `.env`, `execute`, `allocat`
   (case-insensitive substring match)
5. `autocycle_policy.execution_allowed == false` — policy lock confirmed

If **any** check fails, the task is dropped silently and logged to
`data/system/autocycle_report.json` as `FILTERED_OUT`.

**Output:** Filtered list of safe candidate tasks, length ≤ 3

---

## Phase 4 — Task Execution Candidate Selection

**Purpose:** Select up to `max_tasks_per_cycle` (= 3) tasks from the filtered
safe list. Selection is deterministic: tasks are ordered by their queue position
and the first 3 are taken.

**Output:** Final execution candidate list (0–3 tasks)

**Human review checkpoint:**
Before Phase 5 begins, the candidate list is written to
`data/system/autocycle_candidates.json` for human inspection. In the current
implementation, execution stops here and awaits human approval.

**Safety:** No task is executed at this stage. This phase is selection only.

---

## Phase 5 — Test Execution

**Purpose:** For tasks of type `TEST`, run the associated test suite and capture
results. For tasks of type `DOCS` or `SCHEMA`, validate the artifact (e.g. run
the relevant validator) and capture output.

**Allowed operations in this phase:**
- `python -m unittest <test_module>` — run unit tests
- `python -m utils.<validator>` — run offline validators
- Read and write files within the MarketRegimeBot project tree

**Prohibited operations in this phase:**
- Any broker API call
- Any network request to external services
- Any write to another NOVA repository
- Any order submission or execution command
- Any credential read

**Output:** Test/validation results written to `data/system/autocycle_report.json`

---

## Phase 6 — Result Reporting

**Purpose:** Produce a human-readable summary of the cycle run.

**Output artifact:** `data/system/autocycle_report.json`

**Report structure (schema, not implementation):**
```json
{
  "cycle_id": "CYCLE-YYYYMMDD-NNN",
  "timestamp": "ISO-8601",
  "tasks_evaluated": 0,
  "tasks_filtered_out": 0,
  "tasks_selected": 0,
  "results": [],
  "approval_required": true,
  "commit_approved": false,
  "push_approved": false,
  "execution_allowed": false,
  "runtime_effect": false
}
```

**Safety:** This phase writes one local JSON file only. No commits. No pushes.
No external calls.

---

## Phase 7 — Human Approval Gate

**Purpose:** Present the cycle report to the human operator. The autocycle
system halts completely and waits. No automated action proceeds past this gate.

**Gate rules:**
- A human must explicitly review `data/system/autocycle_report.json`
- A human must explicitly approve or reject the proposed changes
- If approved: commit parameters are written to `data/system/autocycle_commit_plan.json`
- If rejected: the cycle is marked `REJECTED` and no further action is taken

**Automation bypass:** There is no mechanism for the autocycle to self-approve.
The approval flag can only be set by a human operator. Any code path that
attempts to set `commit_approved = true` programmatically is a safety violation.

**This gate is permanent.** It applies in every future implementation phase
without exception.

---

## Phase 8 — Commit / Push Gate

**Purpose:** After human approval, execute the approved commit and push — but
only with explicit human confirmation at the terminal.

**Sequence:**
1. Display the full diff of proposed changes to the operator
2. Request explicit confirmation (`y/N`) before `git commit`
3. Request explicit confirmation (`y/N`) before `git push`
4. Any `N` answer aborts the remaining steps immediately

**Automation note:** The commit and push commands themselves are not automated.
They are prepared (message, file list) and presented for the human to approve
and invoke. The autocycle never calls `git commit` or `git push` autonomously.

---

## Data Flow Summary

```
task_queue.json
      │
      ▼
[Phase 1] Read Queue
      │
      ▼
[Phase 2] Classify Tasks
      │
      ▼
[Phase 3] Safety Filter  ──────► filtered_out → autocycle_report.json
      │
      ▼
[Phase 4] Select Candidates (≤3)
      │  └─► autocycle_candidates.json  ◄── HUMAN INSPECTION POINT
      │
      ▼
[Phase 5] Execute Tests / Validators
      │
      ▼
[Phase 6] Write Report → autocycle_report.json
      │
      ▼
[Phase 7] ══ HUMAN APPROVAL GATE ══ (system halts here)
      │         Human reviews report
      │         Human approves or rejects
      │
      ▼ (approved only)
[Phase 8] ══ COMMIT / PUSH GATE ══
              Human confirms diff
              Human confirms commit
              Human confirms push
```

---

## What Autocycle Will Never Do

| Prohibited action | Reason |
|---|---|
| Autonomous commit | Human approval gate (Phase 7) is permanent |
| Autonomous push | Human push gate (Phase 8) is permanent |
| Execute broker logic | Task type filter blocks all BROKER tasks |
| Place orders | Execution filter + `execution_allowed: false` policy |
| Allocate capital | Out of scope for MarketRegimeBot permanently |
| Bypass safety filter | Phase 3 has no override mechanism |
| Self-approve | Approval flag has no programmatic setter |
| Read credentials | Prohibited at all phases |
| Connect to TWS/IBKR | Prohibited at all phases |
| Trigger Telegram execution | Prohibited at all phases |
