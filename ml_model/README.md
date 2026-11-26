# PhishGuard URL Model

This folder holds the URL-detection data and artifacts. The pipelines, results, and
dataset provenance are described in
[`docs/phase5_ml_detection.md`](../docs/phase5_ml_detection.md). The final
untouched evaluation followed
[`docs/final_model_evaluation_plan.md`](../docs/final_model_evaluation_plan.md)
and is complete.

## Final result (2026-11-26)

The current 18-feature model was tested once on **2,000 URLs**. Each one has a
source timestamp after the approved cutoff of 1 September 2026, and none appears
in the model's development data:

- **1,000 phishing URLs** from PhishTank, verified 1 Sep – 22 Nov 2026.
- **1,000 legitimate URLs** from 76 official websites, captured 5–18 Oct 2026 in
  the Common Crawl October 2026 crawl.

These are verification and capture times, not the dates the URLs first appeared
online. See
[the Phase 5 guide](../docs/phase5_ml_detection.md#what-the-dates-mean-and-what-they-do-not-mean).

| Accuracy | Phishing caught (recall) | Legitimate correctly passed | ROC-AUC | PR-AUC |
| --- | --- | --- | --- | --- |
| 83.35% | 775 / 1,000 (77.5%) | 892 / 1,000 (89.2%) | 0.887 | 0.911 |

- **It missed 225 phishing URLs.** Those links would have been called safe.
- **It flagged 108 legitimate pages as phishing.** These are false alarms.

Because the test is balanced (half phishing) and the legitimate side covers only
official websites, these figures do not transfer directly to everyday browsing.
The full explanation, cleaning counts, and limitations are in
[result D of the Phase 5 guide](../docs/phase5_ml_detection.md#d-final_untouched_evaluationjson-the-final-untouched-test).

## Committed contents

| Path | Contents |
| --- | --- |
| `data/demo_urls.csv` | 600 deterministic synthetic URLs (reserved example addresses); pipeline fixture only |
| `artifacts/metrics.json` | Earlier 15-feature model: stratified random split of a 10,000-row external feature dataset (89.24% accuracy) |
| `artifacts/baseline_external_evaluation.json` | Earlier model evaluated on later PhishTank-format phishing URLs and undated legitimate URLs (48.29% accuracy) |
| `artifacts/raw_training_metrics.json` | Current 18-feature raw-URL model: date-separated training, validation, and diagnostic periods (diagnostic 86.92% accuracy, 0.9527 ROC-AUC) |
| `artifacts/final_untouched_evaluation.json` | **Final untouched evaluation** of the current model (2026-11-26): 83.35% accuracy, 0.887 ROC-AUC, on 1,000 phishing and 1,000 legitimate URLs. Written once by `final_evaluation run --final`; never edit or regenerate it. Aggregates only, no test URLs. |
| `final_evaluation/protocol.json` | Approved (2026-11-22) frozen model checksum, threshold, features, cutoff, sampling rules, and Public Suffix List pin for the final evaluation |
| `final_evaluation/historical_sources.json` | Earlier data sources, with checksums, that the final test must not overlap |
| `final_evaluation/test_sources.json`, `official_domains.csv` | Completed provenance of the final test sources (download times, terms, every raw file's SHA-256) and the 120-domain official allowlist |

Only `final_untouched_evaluation.json` is a final untouched evaluation. The other
metrics files are development results. The diagnostic period in
`raw_training_metrics.json` informed model assessment and was never used as the
final test.

## Local-only contents (ignored by Git)

| Path | Contents |
| --- | --- |
| `artifacts/phishguard_url_model.joblib` | Current 18-feature model loaded by the API by default. The final evaluation used SHA-256 `ac1dc5aac4d97333faea4bcf49a8323b55c49d9d7994db1a42f17c9f5cef9edc`; do not retrain or replace it in place. |
| `artifacts/phishguard_url_model_candidate.joblib` | Candidate written by `retrain_raw` before replacement (identical to the current model in the verified local checkout) |
| `artifacts/phishguard_url_model_pre_raw.joblib` | Backup created by `retrain_raw` from an earlier raw-pipeline run (18 features) |
| `artifacts/phishguard_url_model_precomputed.joblib` | Earlier 15-feature precomputed-feature model |
| `data/external/` | External source files. Only `Phishing_Legitimate_full.csv` and `tranco_5674N.zip` are present locally. |
| `data/final/` | Final-test PhishTank snapshot, Common Crawl index records, and converted CSVs. Never committed: only aggregate results are published until PhishTank confirms redistribution terms. Their checksums are in `test_sources.json`. |

A fresh checkout contains none of these files. Record the SHA-256 checksum of any
model used for reported results, because the binary cannot be recovered from Git.

## Feature schema

The extractor returns 19 features. The current model trains on 18 because
`uses_https` is excluded to reduce source leakage between the legitimate and
phishing datasets. The earlier precomputed model used 15 features.

## Provenance gaps

These gaps concern the **training-era** data only. The final-test sources have
complete provenance in `final_evaluation/test_sources.json`.

The publisher, licence, and collection dates of the external feature dataset and
the legitimate-URL archive are not recorded. Neither are the training-era PhishTank
snapshot's download date or terms, or the Tranco licence. Treat these as
**unavailable** until they are verified from source documentation.

## Important limitations

- The synthetic demo data proves only that the pipeline works. Its near-perfect
  score is not evidence of real-world performance.
- The training commands overwrite these artifacts by default. Pass explicit
  output paths when experimenting.
- The classifier uses lexical URL properties only. It never visits, resolves, or
  downloads content from a submitted URL.
