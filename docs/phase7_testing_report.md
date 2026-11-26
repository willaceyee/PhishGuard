# Phase 7 Testing and Report Guide

Phase 7 separates evidence that can be generated automatically from evaluation that requires genuine participants or representative external data.

| Item | Status |
| --- | --- |
| Unit and integration testing | Complete |
| Final report screenshots | Complete |
| Model evaluation | **Complete**: final untouched test run on 2026-11-26 (see below) |
| Usability testing | **Pending**: requires real participants |

## Automated verification completed

The backend suite covers unit, integration, security, machine-learning, simulation, training, and analytics behavior.

Run from `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

The suite enforces at least 85% statement coverage and writes `coverage.xml`. Local verification on 2026-11-26 contains 362 passing tests with 93.18% coverage. The earlier screenshot evidence in [`evidence/test_summary.md`](evidence/test_summary.md) records 316 tests on 2026-11-10.

The frontend quality checks are:

```powershell
cd frontend
npm test
npm run lint
npm run build
```

GitHub Actions repeats backend tests plus frontend tests, lint, and build for pushes to `main` and pull requests targeting `main`.

## Security checks completed

- JWT protection for administration, analytics, results, and detection endpoints
- Password hashing and authenticated password changes
- Generic invalid-login responses
- Configured-origin CORS rather than unrestricted cross-origin access
- Content Security Policy and anti-framing headers
- MIME sniffing, referrer, camera, microphone, and geolocation restrictions
- Credential-free simulation form behavior
- URL analysis that performs no DNS or HTTP requests
- Development debug mode disabled unless explicitly enabled
- Local SQLite database excluded from Git

## Usability-test protocol — participant work pending

Do not mark usability testing complete until real participants perform the study.

Use the complete [`usability_testing_guide.md`](usability_testing_guide.md),
participant-facing [`usability_questionnaire.md`](usability_questionnaire.md),
and anonymous [`usability_results_template.csv`](usability_results_template.csv)
to conduct and record each session consistently.

### Recommended participants

- Six to eight participants, aiming for at least three administrator-role and
  three end-user-role participants
- A mix of technical and non-technical backgrounds
- Participants who did not build the application

Record anonymous participant codes rather than names or email addresses. Obtain informed consent and explain that the phishing flow is a controlled simulation.

### Tasks

Administrator participants test sign-in, user and template management, campaign
creation, dashboard interpretation, and URL detection explanations. End-user
participants test the controlled simulation link, awareness material, quiz, and
the clarity of a prepared SHAP explanation. Exact task wording and completion
conditions are defined in the usability testing guide.

### Measures

- Task completion: success, partial success, or failure
- Completion time in seconds
- Errors and requests for assistance
- One-to-five rating for ease, clarity, confidence, and visual readability
- Open comments: most useful element, most confusing element, and suggested improvement

### Acceptance targets

- At least 80% successful task completion
- Median task completion under two minutes
- Mean clarity and ease ratings of at least 4/5
- No critical issue that prevents login, dashboard interpretation, or logout

Store results in an anonymized table and report both successful and unsuccessful outcomes.

## Real-world model evaluation — complete

The final untouched evaluation ran once on 2026-11-26. Its report is
[`final_untouched_evaluation.json`](../ml_model/artifacts/final_untouched_evaluation.json),
and the full explanation is
[result D in `phase5_ml_detection.md`](phase5_ml_detection.md#d-final_untouched_evaluationjson-the-final-untouched-test).

**Test set:** 2,000 URLs whose source timestamps fall after the approved
2026-09-01 cutoff:

- **1,000 phishing URLs:** PhishTank, with `verification_time` from 1 Sep to
  22 Nov 2026, from 951 websites.
- **1,000 legitimate URLs:** Common Crawl pages with capture timestamps from 5 to
  18 Oct 2026, on 76 ownership-checked official websites in Australia and the US.

Any URL, page pattern, or website that appears in the model's development data
(training, validation, and diagnostic sets) was removed.

These timestamps record when PhishTank verified a report and when Common Crawl
captured a page. Neither is the date a URL first appeared online, so some test
URLs may have existed before the model was trained. The guarantee is that none
of them is in the development data. See
[Phase 5, "What the dates mean"](phase5_ml_detection.md#what-the-dates-mean-and-what-they-do-not-mean).

| | Predicted legitimate | Predicted phishing |
| --- | --- | --- |
| **Actually legitimate** | 892 | 108 (false alarms) |
| **Actually phishing** | 225 (missed) | 775 |

| Accuracy | Phishing precision / recall / F1 | Legitimate precision / recall / F1 | ROC-AUC | PR-AUC |
| --- | --- | --- | --- | --- |
| 83.35% | 0.878 / 0.775 / 0.823 | 0.799 / 0.892 / 0.843 | 0.887 | 0.911 |

In plain terms:

- **The model caught 775 of 1,000 phishing links, and missed 225.** Those 225
  would have been called safe, which is the more serious error. This is why the
  detector is decision support, not a guarantee.
- **It wrongly warned about 108 of 1,000 genuine pages.** These are false alarms:
  less dangerous than misses, but they can make users ignore warnings.
- **The scores are a few points below the August validation figures** (87.92%
  accuracy, 0.955 ROC-AUC). That is expected for post-cutoff data that is absent from the development data, and the
  final figures are the ones to report.

**Threshold rationale.** The threshold stayed at 0.5, as fixed in the approved
protocol before the data was opened. It was not tuned on the test set. A lower
threshold would catch more phishing at the cost of more false alarms. Choosing
one would need new data, because this test set cannot be reused for tuning.

**Limits on how broadly the result applies:**

- The test is **balanced (50% phishing)**. Real traffic has far less phishing, so
  real-world precision would be lower than 87.8%. Recall does not depend on the
  mix.
- The legitimate sample comes from **76 official websites** (finance, education,
  health, non-profit, government, utilities) with at most 20 pages each. It does
  not represent everyday browsing, and government and utility sites are
  under-represented.
- There is **one phishing feed** (verified, still-online PhishTank reports), and
  the model reads **URL text only**.
- **Unsupported URLs were excluded:** 11 were over 2,048 characters or contained
  spaces (2 after the cutoff).
- The results describe URLs with **source timestamps in September–November 2026**.
  Phishing changes over time.

The report was verified against the approved `protocol.json` before this item was
marked complete (25 of 25 checks; see Phase 5, result D). Only aggregate results
are published; the test URL lists are not.

### Earlier development results (not final evidence)

The synthetic development dataset verifies the pipeline only. Do not report its
perfect score as final model performance. The external-data results below came
before the final test. The details are in
[`phase5_ml_detection.md`](phase5_ml_detection.md):

- `metrics.json`: earlier 15-feature model, random split of a 10,000-row external
  feature dataset, 89.24% accuracy. It does not show temporal generalization.
- `baseline_external_evaluation.json`: the same earlier model on later,
  different-source URLs, 48.29% accuracy. The legitimate data has no collection
  dates.
- `raw_training_metrics.json`: current 18-feature model with `uses_https`
  excluded, trained and assessed on date-separated periods. The diagnostic
  period scored 86.92% accuracy and 0.9527 ROC-AUC. It has already informed model
  assessment and cannot be reused as the final untouched test.

The procedure followed for the final test is in
[`final_model_evaluation_plan.md`](final_model_evaluation_plan.md). It met the
general requirements below.

Requirements for the final evaluation:

1. Select an ethically sourced and licensed dataset with collection dates and label definitions.
2. Remove exact and normalized URL duplicates before splitting.
3. Check whether domains or near-duplicate URL templates leak across splits.
4. Preserve an untouched test set; prefer a time-based holdout when timestamps exist.
5. Document class distribution and preprocessing decisions.
6. Train using only the training partition and select settings with validation data.
7. Evaluate once on the untouched test partition.

Report:

- confusion matrix;
- accuracy, precision, recall, and F1 for both classes;
- ROC-AUC and precision-recall AUC;
- false-positive and false-negative counts;
- probability calibration or threshold rationale;
- performance by URL source or collection period when metadata permits;
- limitations, bias, dataset age, and concept-drift risk.

Save the final metrics with the dataset identity, code commit, feature schema, random seed, and model artifact checksum.

## Final report evidence

Completed screenshot evidence is indexed in
[`evidence/screenshots/README.md`](evidence/screenshots/README.md) and includes:

- a CI run showing passing backend and frontend jobs
- the administrator login screen
- the populated analytics dashboard, campaign performance, and user-risk table
- the simulation awareness page and five-question quiz
- a URL prediction response with SHAP factors

The automated coverage summary is recorded in
[`evidence/test_summary.md`](evidence/test_summary.md).

The real-world confusion matrix and metric table from the final untouched
evaluation are recorded above and in
[`final_untouched_evaluation.json`](../ml_model/artifacts/final_untouched_evaluation.json).

Evidence that still requires genuine participants:

- anonymized usability results from participant testing

Screenshots should show no passwords, tokens, personal email addresses, or real tracking URLs.

To prepare anonymous dashboard data in a disposable SQLite database:

```powershell
cd backend
$env:DATABASE_URL = "sqlite:///phase7_evidence.db"
.\venv\Scripts\python.exe -m scripts.seed_evidence
.\venv\Scripts\python.exe run.py
```

The evidence script refuses to seed a database that already contains an administrator. Delete only the disposable `phase7_evidence.db` when you no longer need it; never point the script at your working database.
