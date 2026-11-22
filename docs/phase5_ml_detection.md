# Phase 5 Machine-Learning Detection Guide

Phase 5 implements an offline phishing URL classifier using lexical URL features, a Random Forest model, and SHAP explanations.

> **Evaluation status:** Final model evaluation is **not complete**. None of the
> results below come from a final untouched test set. The plan for that test is
> in [`final_model_evaluation_plan.md`](final_model_evaluation_plan.md); its tooling is
> `python -m app.ml.final_evaluation` (the historical `app.ml.evaluate` baseline command is unchanged).

## Safety boundary

Feature extraction never connects to a submitted URL. It performs no HTTP request, DNS lookup, WHOIS query, page download, or browser navigation. Only the URL text is analyzed.

The prediction API requires an administrator JWT. This prevents the endpoint from becoming an unrestricted public scanning service.

## URL features: 19 extracted, 18 used by the current model

`backend/app/ml/features.py` extracts 19 deterministic features (`FEATURE_NAMES`):

- URL, hostname, path, and query lengths;
- digit, dot, hyphen, at-sign, and percent counts;
- subdomain count and path depth;
- query-parameter and suspicious-keyword counts;
- HTTPS usage (`uses_https`);
- IP-hostname, explicit-port, punycode, and known-shortener flags;
- Shannon character entropy.

The current raw-URL model trains on **18** of them (`MODEL_FEATURE_NAMES`).
`uses_https` is deliberately excluded. HTTPS prevalence differs sharply between
the supplied phishing and legitimate sources, and in particular every Tranco-derived
legitimate URL is built as `https://<host>/`. A model trained on it would partly
learn which source a URL came from rather than whether it is phishing.
`uses_https` is still extracted and returned by the API for transparency, but it
is never a model input and never appears as a SHAP factor.

The earlier precomputed-feature model used 15 features
(`PRECOMPUTED_FEATURE_NAMES`, the first 15 entries, including `uses_https`),
mapped from the columns of an external feature dataset.

## Training pipelines

Three pipelines exist. All run from `backend`.

### 1. Synthetic development fixture

```powershell
.\venv\Scripts\python.exe -m app.ml.prepare_demo_data
```

This creates `ml_model/data/demo_urls.csv` with 300 benign and 300 phishing-like
synthetic examples using reserved example namespaces or documentation IP
addresses. The data is deliberately separable and only proves that extraction,
training, saving, loading, prediction, and SHAP work. Its scores are not evidence
of real-world performance. The automated tests train temporary models of this kind.

### 2. Earlier precomputed-feature model (`app.ml.train`)

`app.ml.train` accepts either a raw `url,label` CSV or the supported precomputed
feature columns. It uses a stratified random 75/25 split and a 300-tree
`RandomForestClassifier` (`max_depth=12`, `min_samples_leaf=2`, balanced class
weights, seed 42). The committed `metrics.json` came from this pipeline run on
`Phishing_Legitimate_full.csv` (see the results below).

### 3. Current raw-URL model (`app.ml.retrain_raw`)

`app.ml.retrain_raw` trains the model that the API currently loads by default
(`ml_model/artifacts/phishguard_url_model.joblib`). It uses the 18 model features,
a 400-tree `RandomForestClassifier` (`max_depth=18`, `min_samples_leaf=2`, balanced
class weights, seed 42) and a fixed 0.5 decision threshold.

- **Phishing URLs:** a PhishTank-format CSV. Only rows marked `verified=yes` and
  `online=yes` are used. Rows are split by `verification_time`:
  - training: before `2026-08-01T00:00:00Z`
  - validation: from `2026-08-01T00:00:00Z` up to `2026-08-22T00:00:00Z`
  - diagnostic: from `2026-08-22T00:00:00Z` onward
- **Legitimate URLs:** split 50/50 between two sources.
  - Rows with `status = 1` from an external legitimate-URL archive.
  - Homepage URLs (`https://<domain>/`, alternating with `https://www.<domain>/`)
    built from a Tranco top-sites list.

  These sources have no per-URL dates. The pipeline assigns legitimate URLs to
  the three splits at random, so the legitimate side is **not** date-separated.
- **Duplicate handling:** exact URL strings only. No normalized-URL deduplication,
  near-duplicate detection, or domain/template leakage check is performed between
  splits.

### Avoiding accidental overwrites

All three training commands overwrite committed evidence when run with their
defaults:

- `app.ml.train` writes `phishguard_url_model.joblib` and `metrics.json`.
- `app.ml.retrain_raw` writes the model, `_candidate` and `_pre_raw` backups, and
  `raw_training_metrics.json`.
- `app.ml.evaluate` writes `unseen_evaluation.json`.
- `app.ml.final_evaluation run --final` writes `final_untouched_evaluation.json` once and
  refuses to overwrite it; development runs must pass a different `--output`.

Always pass explicit `--model`, `--metrics`, or `--output` paths when
experimenting. The `.joblib` files are ignored by Git and exist only in local
checkouts.

## Recorded results

None of these three results is a final untouched evaluation. Each answers a
different question, and they must not be combined or compared as if they used
the same test.

### A. `metrics.json`: random split of the earlier feature dataset

| Item | Value |
| --- | --- |
| Pipeline / model | `app.ml.train`, 15-feature precomputed model |
| Data | `Phishing_Legitimate_full.csv`, 10,000 rows (5,000 per class) |
| Split | Stratified random: 7,500 training rows and 2,500 test rows |
| Accuracy | 89.24% |
| ROC-AUC / PR-AUC | 0.9585 / 0.9547 |
| Confusion matrix `[[TN, FP], [FN, TP]]` | `[[1071, 179], [90, 1160]]` |
| Legitimate precision / recall / F1 | 0.9225 / 0.8568 / 0.8884 |
| Phishing precision / recall / F1 | 0.8663 / 0.9280 / 0.8961 |
| Generated | 2026-08-22T07:21:59Z |

**Limitation:** this split is random, not by date. Training and test rows come
from the same collection, so the result does **not** show that the model
generalizes to phishing URLs that appear later. The feature values were also
calculated by the dataset's own pipeline, which may not match PhishGuard's live
extractor exactly.

### B. `baseline_external_evaluation.json`: earlier model on later, different-source URLs

| Item | Value |
| --- | --- |
| Pipeline / model | `app.ml.evaluate`, applied to the 15-feature model from result A |
| Phishing data | PhishTank-format rows verified after `2026-08-22T07:21:59Z` (the time that model was trained) |
| Legitimate data | `status = 1` rows from the external legitimate-URL archive (no collection dates available) |
| Rows | 2,106 (1,053 per class, randomly sampled with seed 42) |
| Accuracy | 48.29% |
| ROC-AUC / PR-AUC | 0.6049 / 0.5354 |
| Confusion matrix `[[TN, FP], [FN, TP]]` | `[[801, 252], [837, 216]]` |
| Legitimate precision / recall / F1 | 0.4890 / 0.7607 / 0.5953 |
| Phishing precision / recall / F1 | 0.4615 / 0.2051 / 0.2840 |
| Generated | 2026-08-31T06:02:06Z |

**Limitations:**

- The source distribution differs from training. The model learned from
  precomputed features of one dataset but was tested on raw URLs from other
  sources, with features calculated by PhishGuard's extractor.
- Only the phishing side is guaranteed to be later than training. The
  legitimate archive has no collection date, so the legitimate side may be
  older than, or overlap with, the training data.

The result shows that the earlier model did not transfer to new sources: it
missed 837 of 1,053 phishing URLs. It measures cross-source behavior, not
production safety. This result led to development of the raw-URL pipeline.

### C. `raw_training_metrics.json`: current raw-URL model

| Item | Value |
| --- | --- |
| Pipeline / model | `app.ml.retrain_raw`, 18 features (`uses_https` excluded) |
| Training rows | 136,550: 68,275 phishing, 34,137 status-1 legitimate, 34,138 Tranco homepages |
| Threshold | 0.5 |
| Random seed | 42 |
| Rejected rows | PhishTank 12, legitimate archive 235 |
| Generated | 2026-08-31T14:53:06Z |

| Period | Rows | Accuracy | ROC-AUC | PR-AUC | `[[TN, FP], [FN, TP]]` |
| --- | --- | --- | --- | --- | --- |
| Validation (1–22 Aug 2026) | 9,138 | 87.92% | 0.9551 | 0.9597 | `[[4302, 267], [837, 3732]]` |
| Diagnostic (from 22 Aug 2026) | 2,172 | 86.92% | 0.9527 | 0.9579 | `[[1028, 58], [226, 860]]` |

Diagnostic class metrics:

- Legitimate: precision 0.8198, recall 0.9466, F1 0.8786.
- Phishing: precision 0.9368, recall 0.7919, F1 0.8583.

At the fixed 0.5 threshold, the model misses roughly one in five phishing URLs in
both periods.

**The diagnostic period is not a final untouched test.** Its results have already
informed model assessment, so it cannot be reused as the final untouched test.
Further reasons:

- The local `_pre_raw` backup bundle shows that an earlier raw-pipeline run on the
  same day (trained 2026-08-31T14:48:41Z) preceded the recorded run.
- Result B's phishing data, verified after 2026-08-22T07:21:59Z, overlaps the
  same period.
- The legitimate rows in the diagnostic period are not date-separated.
- Exact-string deduplication cannot rule out near-duplicate or same-domain
  leakage between periods.

## Dataset provenance

Information that is not recorded in the repository is marked **Unavailable**. Do
not fill these fields from memory or assumption. Record them only from verified
source documentation.

| Dataset | Used by | Publisher / source | Collection dates | Licence / terms | Local file | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| `Phishing_Legitimate_full.csv` (precomputed features, `CLASS_LABEL` 0/1) | A | Unavailable | Unavailable | Unavailable | Present in `ml_model/data/external/` (Git-ignored) | `204c226d…a8900` (matches local file) |
| PhishTank-format CSV (`url`, `verified`, `verification_time`, `online`) | B, C | Identified as PhishTank by the code only; download date unavailable | Per-row `verification_time`; snapshot date unavailable | Unavailable | Not present | `a55aa3b2…2240` |
| Legitimate-URL archive (one CSV with `url`, `status`; `status = 1` treated as legitimate) | B, C | Unavailable | Unavailable | Unavailable | Not present | `3b888fbf…390ce` |
| `tranco_5674N.zip` (`top-1m.csv`) | C | Tranco top-sites list; the file name suggests list ID `5674N` (not independently verified) | Archive entry dated 2026-08-30 | Unavailable | Present in `ml_model/data/external/` (Git-ignored) | `6ef97b32…a24e4` (matches local file) |

Full checksums are stored in the corresponding metrics JSON files.

## Prediction API

`POST /api/detection/predict`

The endpoint requires an administrator bearer token.

```json
{
  "url": "https://portal.example/account"
}
```

The response includes:

- `prediction`: `phishing` or `legitimate`;
- `phishing_probability` and `confidence`;
- all 19 extracted features;
- the five highest-impact SHAP factors, chosen from the features the loaded model
  was trained on (18 for the current model);
- each factor's value, SHAP impact, and risk direction.

SHAP factors explain this model's decision for the submitted feature vector. They do not prove that a URL is malicious, and users should treat the output as decision support rather than a definitive verdict.

## Automated tests

Tests generate and train a temporary model rather than relying on the ignored local artifact. Coverage includes feature extraction, invalid URL rejection, authentication, missing-model behavior, prediction structure, and SHAP output.
