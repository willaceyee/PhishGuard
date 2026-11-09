# Capstone Alignment Step 1 Design

## Intent

Bring the implemented awareness quiz and automated evidence into agreement with the capstone proposal. The system will have a fixed five-question quiz, GitHub CI will execute the existing frontend tests, and the evidence document will report fresh verified results.

## Goals

- Add one link-inspection question based on the existing training lesson.
- Keep quiz scoring and retry behavior correct with five questions.
- Run frontend tests in GitHub Actions before lint and build.
- Replace stale automated-test counts and coverage with fresh verification evidence.

## Non Goals

- An administrator-managed quiz bank or question editor.
- Changes to the training workflow, risk-score formula, or campaign analytics.
- Participant usability results, awareness-study results, or model-performance claims.
- Changes to the proposal document in this step.

## Constraints

- The new question must assess content already taught on the awareness page.
- Existing quiz records remain valid because each result stores its own total question count.
- Evidence must come from commands run on the final implementation, not estimated values.
- The evidence document must continue to state that participant and awareness evaluation are pending.

## Approaches Considered

### Fixed Five Question Quiz

Add a fifth entry to the existing server-side question tuple, update its tests, and leave the quiz architecture unchanged. This is the selected approach because it directly resolves the proposal mismatch with minimal code.

### Configurable Quiz Bank

Store questions in the database and add administration APIs and screens. This was rejected because it adds models, migrations, and interface work that the proposal does not require.

## Design

The awareness page will separate sender inspection and link inspection into distinct numbered lessons. The quiz will add a `links` question asking users to inspect the real destination and use a trusted route to the service. The correct answer will reflect the lesson wording, and existing validation will continue requiring every question to be answered.

Backend tests will submit five answers, assert a score and total of five, verify incomplete submissions still fail, and verify retry behavior still replaces the previous result. GitHub Actions will run `npm test` after `npm ci`, before lint and build.

After all checks pass, `docs/evidence/test_summary.md` will be updated with the actual backend test count, statement coverage, frontend test-file and test counts, verification date, and the commands used. It will not present usability testing or awareness improvement as completed.

## Acceptance Criteria

- The training page teaches sender and link inspection separately.
- The quiz displays exactly five questions and scores all five.
- Missing any answer returns the existing validation error.
- Retaking the quiz replaces the previous result with a five-question score.
- Backend tests, frontend tests, frontend lint, and frontend production build pass.
- GitHub Actions contains an explicit frontend test step.
- The evidence summary matches the fresh verification output.
