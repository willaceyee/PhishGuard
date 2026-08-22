# Phase 7 Testing and Report Guide

Phase 7 separates evidence that can be generated automatically from evaluation that requires genuine participants or representative external data.

## Automated verification completed

The backend suite covers unit, integration, security, machine-learning, simulation, training, and analytics behavior.

Run from `backend`:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

The suite enforces at least 85% statement coverage and writes `coverage.xml`. Current local verification contains 26 passing tests with 88.55% coverage.

The frontend quality checks are:

```powershell
cd frontend
npm run lint
npm run build
```

GitHub Actions repeats backend tests and frontend lint/build on every push and pull request.

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

### Recommended participants

- Five to eight participants representing intended administrator users
- A mix of technical and non-technical organizational roles
- Participants who did not build the application

Record anonymous participant codes rather than names or email addresses. Obtain informed consent and explain that the phishing flow is a controlled simulation.

### Tasks

1. Sign in as an administrator.
2. Identify the campaign with the highest click-through rate.
3. Identify users prioritized for additional coaching.
4. Explain what contributes to a displayed risk score.
5. Review training completion and quiz performance.
6. Submit a URL for detection and interpret the SHAP factors.
7. Change the administrator password and sign in again.

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

## Real-world model-evaluation protocol — dataset work pending

The synthetic development dataset verifies the pipeline only. Do not report its perfect score as final model performance.

Before final evaluation:

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

Recommended evidence includes:

- CI run showing passing backend and frontend jobs
- coverage summary
- administrator login screen
- populated analytics dashboard
- campaign performance table
- user-risk table and disclosed formula
- simulation awareness page and quiz result
- URL prediction response with SHAP factors
- anonymized usability-results table
- real-world confusion matrix and metric table

Screenshots should show no passwords, tokens, personal email addresses, or real tracking URLs.

To prepare anonymous dashboard data in a disposable SQLite database:

```powershell
cd backend
$env:DATABASE_URL = "sqlite:///phase7_evidence.db"
.\venv\Scripts\python.exe -m scripts.seed_evidence
.\venv\Scripts\python.exe run.py
```

The evidence script refuses to seed a database that already contains an administrator. Delete only the disposable `phase7_evidence.db` when you no longer need it; never point the script at your working database.
