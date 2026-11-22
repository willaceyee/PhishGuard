# PhishGuard URL Model

This folder holds the URL-detection data and artifacts. The pipelines, results, and
dataset provenance are described in
[`docs/phase5_ml_detection.md`](../docs/phase5_ml_detection.md). The plan for the
final, still-pending, untouched evaluation is in
[`docs/final_model_evaluation_plan.md`](../docs/final_model_evaluation_plan.md).

## Committed contents

| Path | Contents |
| --- | --- |
| `data/demo_urls.csv` | 600 deterministic synthetic URLs (reserved example addresses); pipeline fixture only |
| `artifacts/metrics.json` | Earlier 15-feature model: stratified random split of a 10,000-row external feature dataset (89.24% accuracy) |
| `artifacts/baseline_external_evaluation.json` | Earlier model evaluated on later PhishTank-format phishing URLs and undated legitimate URLs (48.29% accuracy) |
| `artifacts/raw_training_metrics.json` | Current 18-feature raw-URL model: date-separated training, validation, and diagnostic periods (diagnostic 86.92% accuracy, 0.9527 ROC-AUC) |
| `final_evaluation/protocol.json` | Frozen model checksum, threshold, features, proposed cutoff, sampling seed, and Public Suffix List pin for the final evaluation (approval pending) |
| `final_evaluation/historical_sources.json` | Earlier data sources, with checksums, that the final test must not overlap |
| `final_evaluation/test_sources.json`, `official_domains.csv` | Provenance template for the final test sources and the official-domain allowlist (to complete before collection) |

None of these metrics is a final untouched evaluation. The diagnostic period in
`raw_training_metrics.json` has already informed model assessment and must not be
reused as the final test.

## Local-only contents (ignored by Git)

| Path | Contents |
| --- | --- |
| `artifacts/phishguard_url_model.joblib` | Current 18-feature model loaded by the API by default |
| `artifacts/phishguard_url_model_candidate.joblib` | Candidate written by `retrain_raw` before replacement (identical to the current model in the verified local checkout) |
| `artifacts/phishguard_url_model_pre_raw.joblib` | Backup created by `retrain_raw` from an earlier raw-pipeline run (18 features) |
| `artifacts/phishguard_url_model_precomputed.joblib` | Earlier 15-feature precomputed-feature model |
| `data/external/` | External source files. Only `Phishing_Legitimate_full.csv` and `tranco_5674N.zip` are present locally. |
| `data/final/` | Raw final-test downloads and converted CSVs (never committed) |

A fresh checkout contains none of these files. Record the SHA-256 checksum of any
model used for reported results, because the binary cannot be recovered from Git.

## Feature schema

The extractor returns 19 features. The current model trains on 18 because
`uses_https` is excluded to reduce source leakage between the legitimate and
phishing datasets. The earlier precomputed model used 15 features.

## Provenance gaps

The publisher, licence, and collection dates of the external feature dataset and
the legitimate-URL archive are not recorded. Neither are the PhishTank snapshot
date or terms, or the Tranco licence. Treat these as **unavailable** until they
are verified from source documentation.

## Important limitations

- The synthetic demo data proves only that the pipeline works. Its near-perfect
  score is not evidence of real-world performance.
- The training commands overwrite these artifacts by default. Pass explicit
  output paths when experimenting.
- The classifier uses lexical URL properties only. It never visits, resolves, or
  downloads content from a submitted URL.
