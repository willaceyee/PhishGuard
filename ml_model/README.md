# PhishGuard URL Model

This folder contains Phase 5 data and generated artifacts.

## Contents

- `data/demo_urls.csv`: 600 deterministic synthetic URLs using reserved example addresses.
- `artifacts/metrics.json`: evaluation output from the local development training run.
- `artifacts/phishguard_url_model.joblib`: generated model bundle, ignored by Git.

## Important limitation

The demo data exists to verify feature extraction, training, saving, loading, prediction, and SHAP integration. Its perfect synthetic test score is not evidence of real-world phishing-detection performance.

Before academic evaluation or deployment, replace it with a documented, ethically sourced, representative dataset containing real benign and phishing URLs. Deduplicate URLs before splitting and consider a time-based holdout to reduce leakage.

The classifier uses lexical URL properties only and never visits, resolves, or downloads content from a submitted URL.
