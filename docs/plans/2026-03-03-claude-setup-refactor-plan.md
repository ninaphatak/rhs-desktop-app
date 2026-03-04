# Claude Setup Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `~/.claude/CLAUDE.md`, project `CLAUDE.md`, and `docs/PRD.md` to wire superpowers workflow globally, slim project config to stable conventions only, and establish repeatable context management.

**Architecture:** Three-file edit — global CLAUDE.md gets workflow mandates that all projects inherit; project CLAUDE.md becomes conventions-only with PRD reference and mock rules; PRD.md gains a living build-state table. No code changes, no new dependencies.

**Tech Stack:** Markdown only. Verification is reading files back and checking structure.

---

### Task 1: Update `~/.claude/CLAUDE.md` (Global Workflow Mandates)

**Files:**
- Modify: `~/.claude/CLAUDE.md`

**Step 1: Replace the file contents**

The file currently contains only an update-memory skill reference. Replace with:

```markdown
# Global Claude Code Settings

## Superpowers Workflow

These rules apply to every project.

### Brainstorm First
Before any feature implementation, the brainstorming skill must run. No code is written
until the user has approved a design. This is a hard gate — not optional.

### Writing-Plans After Brainstorming
Once design is approved, invoke the writing-plans skill. Save the implementation plan to
`docs/plans/YYYY-MM-DD-<feature-name>-plan.md` and commit it before writing any code.

### TDD Review Gate
After writing each test — before writing any implementation code — explain in plain English:
- What behavior the test exercises
- What inputs and outputs it uses
- What specific bug or regression it would catch

Wait for user approval before proceeding to implementation.

### Verify Before Completion
Before claiming anything is done, fixed, or passing: run the relevant command and paste
the full actual output. Never say "this should work" or "tests should pass."
Relevant commands for most projects: `pytest tests/ -v`, or the project's run/test command.

### Git Worktrees for Feature Work
New feature branches start in a worktree via the using-git-worktrees skill.
Do not implement features directly on the working tree.

### Systematic Debugging First
Before proposing any fix for a bug or test failure, invoke the systematic-debugging skill
to find root cause. Do not guess or try random fixes.

---

## Available Skills
When using any of the following skills, check `~/.claude/skills/` for the full instructions.

- **update-memory** — Reads recent JSONL conversation transcripts for the current project
  and updates `memory/MEMORY.md`. Trigger phrases: "update memory", "refresh memory",
  "update my memory file", "sync memory", "summarize my sessions into memory".
  Also available as `/update-memory`.
```

**Step 2: Read back to verify**

Read `~/.claude/CLAUDE.md` and confirm:
- Six workflow sections present (Brainstorm First, Writing-Plans, TDD Review Gate, Verify Before Completion, Git Worktrees, Systematic Debugging)
- update-memory skill reference preserved
- No stray content from old file

**Step 3: Commit**

```bash
git -C ~ add .claude/CLAUDE.md
git -C ~ commit -m "Add superpowers workflow mandates to global CLAUDE.md"
```

---

### Task 2: Update Project `CLAUDE.md` — Remove Current Status, Add PRD Reference

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add PRD reference after "What This App Does" section**

After the line ending `...see \`docs/solenoid_protocol.md\`.`, add:

```markdown
> See `docs/PRD.md` for product requirements and current build state.
```

**Step 2: Remove the "Current Status" section entirely**

Remove this entire block (lines 55–63):

```markdown
## Current Status
- Serial reader + live graphs (4 panels: pressure, flow, HR, temp)
- On-demand CSV recording (Record/Stop buttons, auto-named files)
- In-app matplotlib plotting dialog
- Run quality logging (good/bad/neutral + notes)
- Dual Basler camera panel
- Mock mode (--mock flag for testing without hardware)
- 17 pytest tests passing
- Solenoid control: protocol designed, UI button present but disabled
```

**Step 3: Update Project Structure — add docs/plans reference**

Change the `docs/` line from:
```
- `docs/` — Protocol specs (solenoid_protocol.md)
```
to:
```
- `docs/` — PRD.md (requirements + build state), plans/ (design + implementation plans), solenoid_protocol.md
```

**Step 4: Add Mock Data Rules section after Testing Requirements**

After the existing "## Testing Requirements" section, add:

```markdown
## Mock Data Rules
Do not introduce new mocks or expand mock coverage unless explicitly requested.
`tests/mock_data.csv` and `tests/mock_arduino.py` exist for UI development and demos
only — not for validating data-path logic. Serial data mocks do not accurately represent
hardware behavior.

When mock data is explicitly requested:
1. **Values** — `tests/mock_data.csv` must be sourced from an actual recorded CSV in
   `outputs/`. Do not generate synthetic data.
2. **Timing** — `tests/mock_arduino.py` must use `delay_sec = 0.1 * abs(30.0 / BPM)`.
   `_MOCK_BPM` is managed manually by the user — do not change it.
```

**Step 5: Add Context Management section before Available Skills**

```markdown
## Context Management

| Situation | Action |
|-----------|--------|
| Starting a session | Run `/update-memory` to sync `memory/MEMORY.md` from recent transcripts |
| Picking up mid-feature | Read the relevant `docs/plans/` file — source of truth for where we left off |
| Starting new feature | Brainstorm → design doc → writing-plans → plan saved to `docs/plans/` |
| Finishing a feature | Update PRD.md §12 build state table, run `finishing-a-development-branch`, run `/update-memory` |

**What each file owns:**

| File | Owns | Update frequency |
|------|------|-----------------|
| `CLAUDE.md` | Dev conventions, architecture rules | Rarely |
| `docs/PRD.md §12` | Current build state | Every feature |
| `docs/plans/` | Feature designs + implementation plans | Every feature |
| `memory/MEMORY.md` | Recent session context | Every session |
```

**Step 6: Replace Available Skills section**

Replace the existing "## Available Skills" section with:

```markdown
## Available Skills
When using any of the following skills, check `.claude/skills/` for the full instructions.
Superpowers skills are installed globally — invoke via the Skill tool.

**Project-specific:**
- **arduino-serial-protocol** — 7-field serial format, parsing, CSV output
- **pyqt-threading** — PySide6 QThread patterns for real-time I/O
- **weekly-progress-summary** — Weekly progress slides for BIEN 175B
- **update-memory** — Update memory from conversation transcripts

**Superpowers (global):**
- **superpowers:brainstorming** — Design before code. Always runs before new features.
- **superpowers:writing-plans** — Implementation plan after approved design.
- **superpowers:executing-plans** — Execute a written plan task-by-task.
- **superpowers:systematic-debugging** — Root cause analysis before any fix.
- **superpowers:test-driven-development** — RED-GREEN-REFACTOR with review gate (see global CLAUDE.md).
- **superpowers:verification-before-completion** — Run and paste actual output before claiming done.
- **superpowers:using-git-worktrees** — Isolated worktree for feature branches.
- **superpowers:finishing-a-development-branch** — Structured branch completion and merge.
- **superpowers:subagent-driven-development** — Parallel subagents for independent tasks.
- **superpowers:requesting-code-review** — Code review before merging.
```

**Step 7: Read back to verify**

Read `CLAUDE.md` and confirm:
- No "Current Status" section
- PRD reference present after "What This App Does"
- `docs/` line in Project Structure mentions PRD.md and plans/
- Mock Data Rules section present
- Context Management section with both tables present
- Available Skills section lists both project-specific and superpowers skills

**Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "Refactor CLAUDE.md: remove Current Status, add PRD ref, mock rules, context management, superpowers skills"
```

---

### Task 3: Update `docs/PRD.md` — Add Section 12 Current Build State

**Files:**
- Modify: `docs/PRD.md`

**Step 1: Append Section 12 to the end of the file**

```markdown
## 12. Current Build State

Update this table when features ship. This is the single source of truth for what is
and isn't built — do not track build state in CLAUDE.md.

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
```

**Step 2: Read back to verify**

Read `docs/PRD.md` and confirm:
- Section 12 is present at the bottom
- Table has 9 rows matching the §3 goals
- "Update this table" instruction is present
- All other sections (1–11) are untouched

**Step 3: Commit**

```bash
git add docs/PRD.md
git commit -m "Add Section 12 Current Build State to PRD"
```

---

### Task 4: Final Verification

**Step 1: Verify global CLAUDE.md**

```bash
cat ~/.claude/CLAUDE.md
```
Expected: six workflow sections + update-memory skill. No old content.

**Step 2: Verify project CLAUDE.md**

```bash
grep -n "Current Status\|PRD\|Mock Data\|Context Management\|Superpowers" CLAUDE.md
```
Expected:
- No "Current Status" match
- "PRD" appears in What This App Does and Project Structure and Context Management
- "Mock Data Rules" section heading present
- "Context Management" section heading present
- "Superpowers" appears in Available Skills

**Step 3: Verify PRD.md**

```bash
grep -n "Current Build State\|Done\|Partial\|Not started" docs/PRD.md
```
Expected: Section 12 heading + 9 table rows with status values.

**Step 4: Verify git log**

```bash
git log --oneline -5
```
Expected: three commits from this plan at the top.
