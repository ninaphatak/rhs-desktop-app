# Design: Claude Code Setup Refactor
_Date: 2026-03-03_

## Problem

The current Claude Code setup has no guardrails on planning or brainstorming — features get built
before requirements are clear. CLAUDE.md tracks evolving build state (gets stale). The PRD and
CLAUDE.md don't reference each other. Mocks don't reflect real hardware timing or data. No
structured context management across sessions.

## Goals

1. Wire superpowers workflow globally (brainstorm → plan → TDD with review gate → verify → finish)
2. Slim project CLAUDE.md to stable conventions only — no evolving state
3. Make PRD.md the single source of truth for product requirements + current build state
4. Add explicit mock data rules grounded in real hardware
5. Define a repeatable context management workflow for session boundaries

## Approach: Rich global, thin project

Superpowers workflow rules live in `~/.claude/CLAUDE.md` so every project inherits them
automatically. Project `CLAUDE.md` covers only project-specific conventions. PRD.md gains a
"Current Build State" section that replaces the stale "Current Status" in CLAUDE.md.

---

## Section 1: `~/.claude/CLAUDE.md` (Global)

Add the following workflow mandates that apply to all projects:

### Superpowers Workflow
- **Brainstorm first** — before any feature implementation, the brainstorming skill must run.
  No code is written until the user has approved a design. This is a hard gate.
- **Writing-plans after brainstorming** — once design is approved, invoke writing-plans to
  produce a granular implementation plan saved to `docs/plans/`.
- **Verify before completion** — before claiming anything is done or fixed, run the relevant
  verification command (`pytest tests/ -v`, `bash run.sh --mock`, etc.) and paste actual output.
  Never say "this should work."
- **Git worktrees for feature work** — new feature branches start in a worktree.
- **Systematic debugging first** — before proposing any fix, run systematic-debugging to find
  root cause. No guessing.

### TDD Review Gate (custom — overrides superpowers default)
After writing each test, explain in plain English:
- What behavior the test exercises
- What inputs/outputs it uses
- What specific bug or regression it would catch

User approves before any implementation code is written.

---

## Section 2: Project `CLAUDE.md`

### Removed
- "Current Status" section — moves to PRD.md §12

### Added

**PRD reference** (near top):
> See `docs/PRD.md` for product requirements and current build state.

**Mock data rule:**
> Do not introduce new mocks or expand mock coverage unless explicitly requested. `tests/mock_data.csv`
> and `tests/mock_arduino.py` exist for UI development and demos only — not for validating
> data-path logic. Serial data mocks do not accurately represent hardware behavior.
>
> When mock data is explicitly requested:
> 1. **Values** — `tests/mock_data.csv` must be sourced from an actual recorded CSV in `outputs/`.
>    Do not generate synthetic data.
> 2. **Timing** — `tests/mock_arduino.py` must use `delay_sec = 0.1 * abs(30.0 / BPM)`.
>    `_MOCK_BPM` is managed manually by the user — do not change it.

**Context management workflow:**

| Situation | Action |
|-----------|--------|
| Starting a session | Run `/update-memory` to sync `memory/MEMORY.md` from recent transcripts |
| Picking up mid-feature | Read the relevant `docs/plans/` file — source of truth for where we left off |
| Starting new feature | Brainstorm → design doc → writing-plans → implementation plan (both saved to `docs/plans/`) |
| Finishing a feature | Update PRD.md §12 build state table, run `finishing-a-development-branch`, run `/update-memory` |

**What each file owns:**

| File | Owns | Update frequency |
|------|------|-----------------|
| `CLAUDE.md` | Dev conventions, architecture rules | Rarely |
| `docs/PRD.md §12` | Current build state | Every feature |
| `docs/plans/` | Feature designs + implementation plans | Every feature |
| `memory/MEMORY.md` | Recent session context | Every session |

**Updated skills section** — adds superpowers skills alongside project-specific ones.

**Updated `docs/` description** — mentions PRD.md and plans/.

### Unchanged
Architecture rules, serial protocol table, hardware facts, code style, git workflow,
cross-platform notes, what NOT to build.

---

## Section 3: `docs/PRD.md`

### Added: Section 12 — Current Build State

A table mapping each Section 3 goal to current status. Updated after each feature ships.

| Goal (from §3)              | Status      | Notes                                       |
|-----------------------------|-------------|---------------------------------------------|
| Zero terminal interaction   | Done        | `bash run.sh` / `run.bat`                   |
| Real-time sensor monitoring | Done        | 4 pyqtgraph panels, 30Hz rolling window     |
| Dual camera feeds           | Done        | BaslerCamera QThread, auto-detect           |
| On-demand CSV recording     | Done        | Record/Stop, auto-named, t=0 reset          |
| In-app data visualization   | Done        | PlotDialog, matplotlib, 4 subplots          |
| Run quality logging         | Done        | good/bad/neutral + notes, run_log.csv       |
| Easy setup                  | Done        | setup.sh / setup.bat, environment.yml       |
| Cross-platform              | Partial     | macOS tested; Windows untested              |
| Solenoid control            | Not started | Protocol designed; firmware change needed   |

Nothing else in PRD.md changes.

---

## Implementation Plan

See `docs/plans/2026-03-03-claude-setup-refactor-plan.md` (generated by writing-plans).
