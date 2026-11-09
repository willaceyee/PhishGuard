# Capstone Alignment Step 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the awareness quiz and automated evidence with the capstone proposal by delivering a verified five-question quiz and running frontend tests in continuous integration.

**Architecture:** Keep the existing server-rendered training and quiz flow. Extend its fixed question tuple and lesson content without adding models or migrations, then make the existing frontend test command part of the GitHub Actions quality gate and refresh evidence only from final verification output.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, pytest, React, Vitest, ESLint, Vite, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-11-09-capstone-alignment-step1-design.md`

## Global Constraints

- The fifth question assesses safe link inspection already taught by the awareness page.
- Existing quiz records remain valid because every record stores its own `total_questions` value.
- Do not add a quiz editor, question database table, migration, or new dependency.
- Do not claim participant usability testing, awareness improvement, or model-performance results in automated evidence.
- Do not add assistant or development-tool branding to README files, code, documentation, commit messages, branch names, or review text.
- Commit and push the verified work to `feature/capstone-alignment-step1`; do not merge it into `main` without Willace's approval.

## Review Focus

- A submission missing only `links` must return HTTP 400 and must not create a quiz result.
- A correct five-answer submission must store `score=5`, `total_questions=5`, and report 100 percent.
- A five-answer retry must replace the previous result rather than create a second row.
- Historical results with `score=4` and `total_questions=4` must still calculate as 100 percent.
- The frontend CI job must run tests after dependency installation and before lint and build.

---

### Task 1: Five Question Awareness Quiz

**Files:**
- Modify: `backend/tests/test_training.py`
- Modify: `backend/app/training.py`
- Modify: `backend/app/templates/simulation_training.html`

**Interfaces:**
- Consumes: existing `QUIZ_QUESTIONS`, `/training/<token>`, and `/quiz/<token>` behavior.
- Produces: `QUIZ_QUESTIONS` with exactly five entries, including an entry with `id="links"`; stored quiz results use `total_questions=5` for new submissions.

- [ ] **Step 1: Write failing tests for the fifth question and compatibility**

Update `test_training_quiz_and_admin_results` to assert that the training page contains `Inspect the link destination`, submit the four existing correct answers plus `"links": "a"`, and assert `score == 5`, `total_questions == 5`, and `percentage == 100`.

Update the missing-answer submission to include all existing answers but omit `links`, then assert HTTP 400 and confirm no `QuizResult` was stored.

Update `test_quiz_retry_replaces_previous_result` so both submissions contain five answers and the final stored result has `score == 0`, `total_questions == 5`, and only one result row.

Add this compatibility test:

```python
def test_historical_four_question_result_keeps_its_percentage(app):
    with app.app_context():
        result = QuizResult(score=4, total_questions=4)
        assert result.percentage == 100
```

- [ ] **Step 2: Run the focused tests and verify the new expectations fail**

Run:

```powershell
cd backend
rtk proxy .\venv\Scripts\python.exe -m pytest tests/test_training.py -q
```

Expected: failures show that `links` and the fifth lesson do not exist and new results still total four questions; the historical compatibility test passes.

- [ ] **Step 3: Add the fifth lesson and question**

In `simulation_training.html`, split the current sender-and-link lesson into:

- `1. Inspect the sender`
- `2. Inspect the link destination`

Renumber urgency, trusted-channel verification, and reporting as lessons 3 through 5. The link lesson must instruct the user to inspect the real destination and use a trusted bookmark or official application when possible.

In `training.py`, add this fifth question to `QUIZ_QUESTIONS`:

```python
{
    "id": "links",
    "prompt": "Before opening a link in an unexpected email, what should you do?",
    "choices": (
        ("a", "Inspect the real destination and use a trusted route to the service"),
        ("b", "Trust it whenever the address begins with HTTPS"),
        ("c", "Open it if the message uses a familiar logo"),
    ),
    "correct": "a",
    "explanation": "Inspect the destination first and use a known bookmark or official application when possible.",
}
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run the same focused pytest command. Expected: all tests in `test_training.py` pass.

- [ ] **Step 5: Commit the quiz change**

```powershell
rtk git add backend/tests/test_training.py backend/app/training.py backend/app/templates/simulation_training.html
rtk git commit -m "Add fifth awareness quiz question"
```

### Task 2: Frontend Tests in Continuous Integration

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the existing `npm test` script in `frontend/package.json`.
- Produces: a frontend CI sequence of `npm ci`, `npm test`, `npm run lint`, and `npm run build`.

- [ ] **Step 1: Record the missing CI test gate**

Run:

```powershell
rtk rg -n "npm (ci|test|run lint|run build)" .github/workflows/ci.yml
```

Expected before the change: `npm ci`, lint, and build are present; `npm test` is absent.

- [ ] **Step 2: Add the frontend test step**

Add `- run: npm test` immediately after `- run: npm ci` in the frontend job. Do not change action versions, Node version, triggers, permissions, or backend steps.

- [ ] **Step 3: Verify the local frontend quality sequence**

Run:

```powershell
cd frontend
rtk npm test
rtk npm run lint
rtk npm run build
```

Expected: Vitest, ESLint, and Vite all exit successfully.

- [ ] **Step 4: Verify the workflow command order**

Run the same `rg` command from Step 1. Expected order: `npm ci`, `npm test`, `npm run lint`, `npm run build`.

- [ ] **Step 5: Commit the CI change**

```powershell
rtk git add .github/workflows/ci.yml
rtk git commit -m "Run frontend tests in CI"
```

### Task 3: Fresh Automated Evidence and Branch Delivery

**Files:**
- Modify: `docs/evidence/test_summary.md`
- Modify: `docs/phase7_testing_report.md`

**Interfaces:**
- Consumes: final backend pytest coverage output, frontend Vitest output, lint result, and build result.
- Produces: consistent evidence documents containing the same verified counts, coverage, date, commands, and pending-evaluation limitations.

- [ ] **Step 1: Run the full backend verification**

```powershell
cd backend
rtk proxy .\venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass and statement coverage remains at or above 85 percent. Record the exact test count and coverage displayed by this run.

- [ ] **Step 2: Run the complete frontend verification**

```powershell
cd frontend
rtk npm test
rtk npm run lint
rtk npm run build
```

Expected: all frontend test files and tests pass, ESLint succeeds, and Vite builds successfully. Record the exact test-file and test counts.

- [ ] **Step 3: Update both evidence documents from the recorded output**

In `docs/evidence/test_summary.md`:

- set the verification date to the actual execution date;
- replace the stale backend count and coverage with the exact Step 1 values;
- add the exact frontend test-file and test counts before the lint/build results;
- retain the participant-testing, real-world evaluation, and screenshot limitations.

In `docs/phase7_testing_report.md`:

- replace its stale current backend count and coverage with the same Step 1 values;
- state that the frontend checks include `npm test`, lint, and build;
- retain the statement that participant usability work is pending.

- [ ] **Step 4: Verify evidence consistency and repository wording**

```powershell
rtk rg -n "passed|coverage|npm test|participant.*pending" docs/evidence/test_summary.md docs/phase7_testing_report.md
rtk git diff --check
```

Expected: both evidence documents show the same backend results, both describe frontend tests, pending participant work remains explicit, and `git diff --check` reports no errors.

- [ ] **Step 5: Commit the evidence update**

```powershell
rtk git add docs/evidence/test_summary.md docs/phase7_testing_report.md
rtk git commit -m "Refresh capstone test evidence"
```

- [ ] **Step 6: Confirm the branch contains only intended work**

```powershell
rtk git status --short --branch
rtk git diff --stat main...HEAD
rtk git log --oneline main..HEAD
```

Expected: the worktree is clean and the branch contains only the approved design, implementation plan, quiz, CI, and evidence changes.

- [ ] **Step 7: Push the review branch**

```powershell
rtk git push -u origin feature/capstone-alignment-step1
```

Expected: the remote feature branch is created or updated successfully; do not merge it into `main`.
