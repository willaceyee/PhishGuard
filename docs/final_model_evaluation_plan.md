# Final Untouched Model-Evaluation Plan

Status: **planned and not started.** No final test data has been collected or
opened. "Model evaluation" remains unchecked in
[`cp2_feature_checklist.md`](cp2_feature_checklist.md) until this plan has been
carried out and its results recorded.

## Purpose

Measure the current 18-feature raw-URL model once, on phishing and legitimate
URLs that no earlier training, validation, diagnostic, or baseline run has seen.
The existing results in [`phase5_ml_detection.md`](phase5_ml_detection.md) do not
meet this requirement:

| Existing result | Why it cannot be the final test |
| --- | --- |
| `metrics.json` | Random split of a single feature dataset; no temporal separation |
| `baseline_external_evaluation.json` | Evaluates the earlier 15-feature model, not the current one; legitimate data is undated |
| `raw_training_metrics.json` diagnostic period | Has already informed model assessment; legitimate data is not date-separated |

## 1. Model to evaluate (freeze before collecting data)

Record these values before any test data is downloaded:

- model file and SHA-256 checksum (the current local
  `phishguard_url_model.joblib` was recorded as `ac1dc5aac4d97333faea4bcf49a8323b55c49d9d7994db1a42f17c9f5cef9edc`;
  confirm it again on the evaluation machine);
- feature schema: the 18 `MODEL_FEATURE_NAMES`, with `uses_https` excluded;
- decision threshold: 0.5, as stored in the bundle;
- random seed used for any sampling;
- Git commit of the evaluation code.

If the model file is lost or retrained, the frozen record is no longer valid, and
this plan must be restarted with the new model.

## 2. Cutoff

- Choose one final cutoff timestamp (UTC) and write it in this document **before**
  collecting test data.
- The cutoff must be later than all previously assessed data. The latest recorded
  activity on earlier data is the raw-pipeline run generated at
  2026-08-31T14:53:06Z. The PhishTank snapshot date is unavailable, but that
  snapshot cannot contain entries verified after this run. The cutoff must
  therefore be no earlier than **2026-09-01T00:00:00Z**.
- Both phishing and legitimate URLs must have been first collected or verified
  **after** the cutoff. This also places them well after the diagnostic start
  (2026-08-22T00:00:00Z).

Chosen cutoff: **not yet set**.

## 3. Data sources

For each source, document all of the following before use. Any item that cannot
be verified is a blocker, not a field to estimate:

- publisher and access URL;
- download date and per-URL collection or verification dates;
- label definition (what counts as phishing and as legitimate) and how labels were
  confirmed;
- licence or terms of use, including whether redistribution and academic
  publication are allowed;
- SHA-256 checksum of the downloaded file.

Requirements:

- **Phishing:** verified phishing URLs with verification timestamps after the
  cutoff.
- **Legitimate:** URLs with a documented collection date after the cutoff.
  - Do not reuse the earlier undated legitimate archive or the 2026-08-30 Tranco
    list.
  - Include full URLs with paths and query strings, not only homepages. If all
    legitimate URLs are homepages, the model can separate the classes by URL
    shape alone.

## 4. Cleaning and leakage controls

Apply these steps, in this order, before any prediction is made:

1. Normalize URLs: lower-case the scheme and host, remove default ports and
   fragments, and apply consistent trailing-slash handling. Then remove exact
   duplicates.
2. Remove near-duplicates, such as URLs that differ only in random tokens, IDs, or
   query values, using a documented rule like a path/query template.
3. Remove any test URL whose normalized form, or whose registered domain, appears
   in the earlier training, validation, or diagnostic data, or in the baseline
   evaluation data.
4. Check for template leakage: report how many test URLs share a host or path
   template with training data before step 3, and how many remain after it.
5. Remove URLs that appear in both classes.
6. Record the rows removed at each step and the final class distribution.

## 5. Test procedure

1. Implement and unit-test the loaders and cleaning steps using non-test data
   only.
2. Commit the evaluation code and record its commit hash.
3. Open the test set once and run the frozen model.
4. **No tuning after opening the test set.** Do not change the threshold,
   features, cleaning rules, data selection, or model, and do not rerun the test
   with variations. Any later change requires new data collected after a new
   cutoff.

## 6. Required report

- Confusion matrix in `[[TN, FP], [FN, TP]]` form, with false-positive and
  false-negative counts stated explicitly;
- accuracy;
- precision, recall, and F1 for the legitimate class and for the phishing class;
- ROC-AUC and PR-AUC;
- row counts per class and per source, and the rows removed by each cleaning step;
- model SHA-256 checksum, evaluation-code commit, random seed, feature schema, and
  threshold;
- dataset sources, dates, label definitions, licences, and checksums;
- performance by source or collection week when the metadata allows;
- limitations, covering:
  - **bias:** source coverage, language and region, brand concentration, the
    homepage-versus-path balance, and class balancing;
  - **concept drift:** phishing patterns change quickly, so the result applies to
    the collection window only;
  - **lexical-only scope:** the model sees no page content, hosting, or
    reputation data;
  - **label noise** in the external sources.

Report the result whether it is strong or weak. Earlier results must not be
substituted for it.

## Tooling gaps to resolve before step 5

The existing `app.ml.evaluate` module is not yet sufficient:

- it removes exact duplicates only and has no normalized-URL, near-duplicate, or
  domain-leakage checks;
- its legitimate loader expects the earlier `url,status` archive format;
- its output omits the model checksum and the code commit.

These changes require approval as separate code work and must be finished and
tested before the test set is opened.
