# Phase 5 Machine-Learning Detection Guide

Phase 5 implements an offline phishing URL classifier using lexical URL features, a Random Forest model, and SHAP explanations.

> **Evaluation status:** The final untouched evaluation is **complete** (run once
> on 2026-11-26). The current model scored **83.35% accuracy, 0.887 ROC-AUC and
> 0.911 PR-AUC** on 2,000 URLs whose source timestamps fall after the approved
> 2026-09-01 cutoff and that are absent from its development data. It caught
> 775 of 1,000 phishing URLs and correctly passed 892 of 1,000 legitimate pages.
> See [result D](#d-final_untouched_evaluationjson-the-final-untouched-test) and
> [`final_model_evaluation_plan.md`](final_model_evaluation_plan.md). Results A–C
> below are earlier development results and are not final evidence.

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

Results A–C are development results; only result D is the final untouched
evaluation. Each answers a different question, and they must not be combined or
compared as if they used the same test.

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

### D. `final_untouched_evaluation.json`: the final untouched test

This is the project's final evidence of model performance. The rules (model,
threshold, cutoff, sources, cleaning, sample sizes, seed) were approved and
committed on 2026-11-22, **before** any test data was downloaded. The test ran
exactly once, from commit `f696db3`, and its report can never be overwritten.

**In one sentence:** on URLs whose source timestamps fall after the cutoff and
that do not appear in its development data, the model caught about 3 in 4
phishing links and wrongly flagged about 1 in 9 legitimate pages.

#### What was tested

| Item | Phishing (positive class) | Legitimate |
| --- | --- | --- |
| Source | PhishTank `online-valid` snapshot, downloaded 2026-11-22 | Common Crawl October 2026 crawl (`CC-MAIN-2026-43`), index records downloaded 2026-11-26 |
| Label rule | Verified as phishing by the PhishTank community and still online | Captured page (HTTP 200, HTML) on one of 120 official domains, ownership-checked in government or regulator registers |
| Timestamp used | PhishTank `verification_time` | Common Crawl capture timestamp |
| Timestamps of evaluated URLs | 1 Sep – 22 Nov 2026 | 5–18 Oct 2026 |
| Usable after cleaning | 2,830 (2,497 domains) | 1,158 (76 domains) |
| Evaluated (seed 42) | **1,000** from 951 domains | **1,000** from 76 domains |

The legitimate sample by sector: finance 264, education 213, health 210,
non-profit 181, transport and utilities 67, government 65. By country: Australia
538, United States 462.

Model: the 18-feature Random Forest (SHA-256 `ac1dc5aa…`, trained
2026-08-31), with the fixed 0.5 threshold. Cutoff: only rows whose source
timestamp is after 2026-09-01T00:00:00Z.

#### What the dates mean, and what they do not mean

The cutoff is applied to each source's own timestamp. Neither timestamp is the
date a URL first appeared on the internet.

- **Phishing: `verification_time`.** This is when PhishTank's community confirmed
  the report as phishing. The URL may have been live, or reported, before then.
- **Legitimate: crawl capture timestamp.** This is when Common Crawl fetched the
  page in October 2026. The page may have existed for years before that.

So the test does **not** show that every URL was created after the model was
trained. Two things are guaranteed instead:

1. **Every timestamp is after the approved cutoff.** The cutoff falls after
   every dated training-era record, as recorded in `protocol.json`: the latest
   PhishTank verification time in the training-era snapshot
   (2026-08-31T02:02:21Z), the Tranco list date (2026-08-30), and the model's
   training run (2026-08-31T14:53:06Z). The training-era legitimate archive has
   no dates, which is why overlap with it is checked directly (point 2).
2. **No test URL appears in the model's development data.** That data is what was
   used to train, validate, and diagnose the model. "Appears" is checked three
   ways: by normalized URL, by page pattern, and by registrable domain (see the
   cleaning table below).

In this guide, "unseen" means exactly this: not present in the development data.
It does not mean "created after training".

#### How the data was cleaned

Every step is counted in the report. Rows removed:

| Step | Phishing | Legitimate |
| --- | --- | --- |
| Model cannot read the URL (over 2,048 characters or contains spaces; excluded at conversion) | 11 | 0 |
| Source timestamp on or before the cutoff | 39,560 | 0 |
| Exact duplicates after normalization | 48 | 0 |
| Near-duplicates (same site and page pattern) | 73 | 509 |
| URL already in the training-era data | 7 | 0 |
| Website (registrable domain) already in the training-era data | 445 | 0 |
| Same URL labelled both ways | 0 | 0 |
| More than 20 per website | 0 | 734 |
| Balanced sampling down to 1,000 per class | 1,830 | 158 |

After cleaning, no test URL shares a website or page pattern with the data
the model was trained, validated, or diagnosed on. Before cleaning, 173 did.

#### Results

| Measure | Value | Plain meaning |
| --- | --- | --- |
| Accuracy | 83.35% | 1,667 of 2,000 URLs classified correctly |
| Phishing recall | 77.5% | Share of phishing URLs caught |
| Phishing precision | 87.8% | When the model says "phishing", how often it is right |
| Phishing F1 | 0.823 | Balance of the two measures above |
| Legitimate recall | 89.2% | Share of legitimate pages correctly left alone |
| Legitimate precision | 79.9% | When the model says "legitimate", how often it is right |
| Legitimate F1 | 0.843 | |
| ROC-AUC | 0.887 | How well the scores rank phishing above legitimate, at any threshold (0.5 = guessing, 1.0 = perfect) |
| PR-AUC (average precision) | 0.911 | The same, focused on the phishing class (0.5 = guessing on this balanced set) |

| | Predicted legitimate | Predicted phishing |
| --- | --- | --- |
| **Actually legitimate (1,000)** | 892 correct | **108 false alarms** |
| **Actually phishing (1,000)** | **225 missed** | 775 caught |

The report counts errors but does not analyse individual URLs, so the likely
causes below are explanations from how the model works, not measured findings.

**The 225 missed phishing URLs (false negatives)** are the more serious error.
A missed phishing link is one the tool would call safe. The model reads only the
characters of a URL, so a phishing link that looks ordinary (short, few digits
or symbols, no suspicious words) is likely to look legitimate to it. Missing 22.5%
means PhishGuard's detector should support, not replace, user judgement and
other defences.

**The 108 legitimate URLs incorrectly flagged (false positives)** are false
alarms. A user would be warned about a genuine page. That is less dangerous
than a miss, but frequent false alarms teach users to ignore warnings. Long
URLs with many path segments or query parameters, which official sites often
use, can look suspicious to a URL-only model.

#### Compared with earlier results

| | Validation (Aug 2026, result C) | Final test |
| --- | --- | --- |
| Accuracy | 87.92% | 83.35% |
| Phishing recall | 81.7% | 77.5% |
| ROC-AUC | 0.955 | 0.887 |

The final test is a few points lower on every measure. That is expected and
is the reason for an untouched test. The validation data came from the same
sources and period as training. The final test instead uses:

- source timestamps after the cutoff;
- a different legitimate source;
- no website from the development data. The final
figures are the ones to report.

By week, phishing recall ranged from 62% to 85% (21 to 251 URLs per week),
with no steady decline across September to November.

#### How far the results apply

- **The test is balanced (50% phishing).** Real traffic contains far less
  phishing. At a lower phishing share, the same model would produce relatively
  more false alarms per correct warning, so precision would be lower than 87.8%.
  Recall (the share of phishing caught) does not depend on this mix.
- **The legitimate sample is narrow.** It comes from 76 official websites of
  schools, banks, health services, charities and US government and utility
  bodies in Australia and the US, with at most 20 pages each. It does not
  represent everyday browsing (shopping, social media, news, personal sites).
  Government and utilities are under-represented because 26 of their 40 domains
  had no usable captures, probably because they only redirect, and redirects are
  excluded.
- **One phishing feed.** PhishTank lists community-reported, verified phishing
  that was still online at download time. Short-lived campaigns and phishing that
  is never reported are missing.
- **The model only sees URL text.** No page content, hosting, certificate, or
  reputation data is used.
- **Unsupported URLs.** URLs over 2,048 characters or containing spaces
  (11 in the feed, 2 after the cutoff) cannot be scored and were excluded, so the
  result says nothing about them.
- **Time.** The result describes URLs with source timestamps in
  September–November 2026. Some may have existed earlier (see "What the dates
  mean"). Phishing changes over
  time (concept drift), so performance should be re-checked on newer data.
- **Labels can be wrong.** A compromised official page could be labelled
  legitimate, and in-page redirects cannot be seen in crawl records.
- **Out of scope.** Overlap with the earlier feature-only dataset (result A)
  could not be checked because it contains no URLs; the evaluation makes no claim
  about the earlier 15-feature model.

#### Verification

Before this result was marked complete, the report was checked against
`protocol.json` (25 of 25 checks passed):

- Protocol: unchanged since the run, and approved before the first download.
- Model: its checksum, threshold, and 18 features match the protocol.
- Sampling rules: the cutoff, seed, size limits, per-domain cap, and Public Suffix
  List pin all match.
- Scope: matches the protocol.
- Code: the run used final mode on a clean commit that is part of `main`.
- Inputs: all 122 input-file checksums match.
- Overlap: no historical source was left unchecked, and nothing overlaps after
  cleaning.
- Sizes: both classes are at least 500, and 1,000 were evaluated per class.
- Cleaning: the steps ran in the approved order.
- Metrics: they recompute exactly from the confusion matrix.

Publication: only aggregate results are published. The PhishTank and Common
Crawl URL lists stay out of Git until PhishTank confirms redistribution terms.

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

The two final-test sources (result D) have complete provenance in
[`test_sources.json`](../ml_model/final_evaluation/test_sources.json):

- the publisher, access and documentation URLs, and terms;
- the label definition and download time;
- the SHA-256 of every raw file.

| Dataset | Used by | Publisher / source | Collection dates | Licence / terms | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| PhishTank `online-valid.csv` | D | PhishTank, operated by Cisco Talos | Downloaded 2026-11-22T10:56:20Z; per-row `verification_time` | Free use stated; attribution and redistribution not stated, so aggregates only (plan section 6.2) | `c1db91b4…acf8` |
| Common Crawl `CC-MAIN-2026-43` index records for 120 official domains | D | Common Crawl Foundation | Crawled 2026-10-05 to 2026-10-18; downloaded 2026-11-26 | Common Crawl Terms of Use | Request log `725d58a4…499c`, plus one checksum per domain file |

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
