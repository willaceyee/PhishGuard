# Final Untouched Model-Evaluation Plan

Status: **tooling ready for review; data collection not authorized.** No final test
data has been collected or opened. "Model evaluation" remains unchecked in
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

## 1. Frozen model (verified 2026-11-22)

All values below are also recorded in
[`ml_model/final_evaluation/protocol.json`](../ml_model/final_evaluation/protocol.json),
and the evaluator refuses to run if the local model differs.

| Item | Value |
| --- | --- |
| Model file | `ml_model/artifacts/phishguard_url_model.joblib` (Git-ignored) |
| SHA-256 | `ac1dc5aac4d97333faea4bcf49a8323b55c49d9d7994db1a42f17c9f5cef9edc` (matches) |
| Bundle `trained_at` | 2026-08-31T14:53:06Z (same run as `raw_training_metrics.json`) |
| Features | 18 `MODEL_FEATURE_NAMES` in bundle order; `uses_https` excluded |
| Threshold | 0.5, as stored in the bundle |
| Random seed | 42 (balanced sampling) |
| Evaluation-code commit | Recorded automatically in the report; final mode requires a clean working tree |

If the model file is lost or retrained, this record is no longer valid and the
plan restarts with the new model.

## 2. Cutoff

**Proposed: `2026-09-01T00:00:00Z`** (not yet approved).

- The latest recorded activity on earlier data is the raw-pipeline run generated
  at 2026-08-31T14:53:06Z. The baseline run was generated at
  2026-08-31T06:02:06Z, and the Tranco archive entry is dated 2026-08-30. The
  PhishTank snapshot was used in both runs, so it cannot contain entries verified
  after them.
- The PhishTank snapshot file itself is not on this machine, so its latest
  `verification_time` has not been read directly. Confirm it once the file is
  supplied (the historical-source check will read it).
- A row is kept only if its `observed_at` is **strictly after** the cutoff. Rows
  at or before the cutoff are removed and counted.
- **PhishVN v5** (November 2026 release) is excluded: it reuses August 2026 data
  and is not a temporal holdout.

## 3. Input format

One or more UTF-8 CSV files with a header row. Required columns (extra columns are
allowed and ignored):

| Column | Accepted values |
| --- | --- |
| `url` | A full URL starting with `http://` or `https://`, with a host, no whitespace, at most 2048 characters, and accepted by the feature extractor. Scheme-less URLs are rejected. |
| `label` | Exactly `phishing` or `legitimate` (lower case). Anything else (`1`, `0`, `Phishing`, `benign`) is rejected. |
| `source` | A source name declared in [`test_sources.json`](../ml_model/final_evaluation/test_sources.json). Every row must match its source's declared label. |
| `observed_at` | UTC verification or observation time as ISO 8601 with seconds and an offset, for example `2026-10-07T13:45:00Z` or `2026-10-07T15:45:00+02:00`. Date-only, naive, and future timestamps are rejected. |

In final mode, any malformed row stops the run (fix the file and validate again).

## 4. Cleaning rules (applied in this order, every removal counted by class and source)

1. **Validation and cutoff.** Malformed rows are reported by line number, without
   echoing the URL. Rows at or before the cutoff are removed.
2. **Normalize, then remove exact duplicates.** Identity form: scheme and host
   lower-cased; host converted to IDNA ASCII with any trailing dot removed;
   default ports (80/443) removed; fragment removed; empty path becomes `/`;
   trailing slashes removed from longer paths; percent-escapes upper-cased;
   userinfo and query kept. Within a label, the earliest `observed_at` is kept
   (ties: smallest normalized URL).
3. **Near-duplicates.** Key = host without a leading `www.` + templated path + the
   sorted set of query-parameter names (values ignored; scheme and port ignored).
   Each path segment is lower-cased. All-digit segments become `{n}`. UUIDs become
   `{uuid}`. Hex strings of 8 or more characters containing a digit become
   `{hex}`. Tokens of 16 or more `[a-z0-9_-.=~]` characters with both letters and
   digits become `{token}`. Any remaining run of 2 or more digits becomes `{n}`.
   One row per key and label is kept, using the same tie rule as step 2.
4. **Historical overlap.** A row is removed if any URL it represents matches a
   historical normalized URL. Remaining rows are then removed if their
   registrable domain appears in any historical source. Registrable domains come
   from the Public Suffix List bundled in `publicsuffixlist==1.1.2.20261107` and
   are never downloaded at run time. Multi-part suffixes such as
   `example.co.uk` are handled, and private-section suffixes are included, so
   `tenant.github.io` is its own domain. IP literals are compared as-is. The
   report also counts test rows sharing a host or a path template with historical
   data, before and after this step.
5. **Conflicting labels.** Normalized URLs observed with both labels are removed
   from both classes. This includes a URL hidden behind a near-duplicate
   representative.
6. **Balanced sampling.** Each class is sorted by normalized URL, then
   `min(n_legitimate, n_phishing)` rows are drawn from each with
   `random.Random(42).sample`. The run fails if either class is empty, or below
   the protocol minimum (100 rows per class), after cleaning.

## 5. Historical sources (overlap exclusion)

Listed in
[`ml_model/final_evaluation/historical_sources.json`](../ml_model/final_evaluation/historical_sources.json).
Each raw file is verified against the SHA-256 recorded in the earlier metrics.
Final mode **refuses to run** unless every source is verified or carries a
recorded out-of-scope decision. It never reports the holdout as disjoint on the
basis of a partial check.

| Source | Used by | Status on this machine |
| --- | --- | --- |
| PhishTank-format snapshot `a55aa3b2…52240` | Baseline (B) and raw training, validation, diagnostic (C) | **Missing.** Place it at `ml_model/data/external/phishtank_snapshot_2026_08.csv` (or edit the path). |
| Legitimate `url,status` archive `3b888fbf…390ce` | B and C | **Missing.** Place it at `ml_model/data/external/legitimate_status_archive.zip`. |
| `tranco_5674N.zip` `6ef97b32…a24e4` | C (36,966 homepages: 34,138 / 2,285 / 543) | Present. Rebuilding exactly which entries were used needs the PhishTank snapshot. The split sizes are checked against the recorded run. |
| `Phishing_Legitimate_full.csv` `204c226d…a8900` | A (earlier 15-feature model) | Present, but has **no URL column**, so overlap cannot be checked. Needs a decision (see section 8). |
| Synthetic demo fixture | Pipeline fixture and tests | Regenerated deterministically (`generate_demo_rows(300, seed=42)`). |

Each historical file is checked in full (all rows, regardless of status or
verified/online flags), except Tranco. For Tranco, only the homepages
`app.ml.retrain_raw` actually drew are checked: excluding the whole top-1M list
would remove nearly every official domain.

If a raw file must stay on another machine, run `build-exclusions` there. Copy the
resulting JSON (normalized URLs, registrable domains, hosts, and templates,
bound to the source's checksum) and record its SHA-256 under that source's
`exclusion_list` entry.

## 6. Data acquisition checklist (complete before collection)

### Phishing: PhishTank verified-online feed

- [ ] Source: `https://data.phishtank.com/data/online-valid.csv`
  ([developer information](https://phishtank.org/developer_info.php)). Columns:
  `phish_id, url, phish_detail_url, submission_time, verified, verification_time, online, target`.
  The file contains only verified, currently online phishes and is regenerated
  hourly.
- [ ] Register an application key for automated downloads. Without a key, only a
  few downloads per day are allowed. PhishTank asks for a descriptive User-Agent
  (`phishtank/<username>`).
- [ ] Download **one** snapshot. Record the UTC download time and SHA-256 in
  `test_sources.json` (`snapshot_downloaded_at_utc`, `raw_files`).
- [ ] **Terms: not yet established.** The developer page states no licence,
  attribution, or redistribution terms. Its "Terms of Use" link points to a
  general Cisco end-user licence agreement that does not mention PhishTank.
  Record the applicable terms (or a written confirmation) in `terms` before use.
  Do not redistribute the URL list until this is settled.
- [ ] `observed_at` = per-row `verification_time`. Rows verified at or before the
  cutoff are removed.
- [ ] Coverage limitation: online-only. Phishes taken down before the snapshot are
  absent, so short-lived campaigns are under-represented. Coverage is
  community-submitted and brand-concentrated.

### Legitimate: Common Crawl CC-MAIN-2026-43

- [ ] Crawl `CC-MAIN-2026-43`: 2.16 billion pages crawled 2026-10-05 to 2026-10-18
  ([announcement](https://www.commoncrawl.org/blog/october-2026-crawl-archive-now-available)).
  URL index: `crawl-data/CC-MAIN-2026-43/cc-index.paths.gz` (CDXJ) or
  `cc-index-table.paths.gz` (columnar). The announcement does not state the CDX
  index-server URL; confirm the collection is listed on Common Crawl's index
  server before querying. Querying the index never contacts the listed sites.
- [ ] Terms: [Common Crawl Terms of Use](https://commoncrawl.org/terms-of-use)
  (last updated 2024-03-07). They grant a limited, non-exclusive licence. Crawled
  content may carry separate terms from its owners. No clause specifically covers
  redistributing URL lists.
- [ ] **Benign-label rule.** A crawl timestamp or an HTTP 200 alone does **not**
  make a URL legitimate. A capture is labelled legitimate only if all of these
  hold (enforced by `convert-common-crawl`):
  1. its host is an allow-listed official registrable domain, or a subdomain of
     one;
  2. it has HTTP status 200 and an HTML MIME type;
  3. it has no userinfo, IP host, or non-default port;
  4. its registrable domain does not appear in the PhishTank snapshot.
- [ ] **Official-domain allowlist**
  ([`official_domains.csv`](../ml_model/final_evaluation/official_domains.csv)):
  columns `domain, organization, sector, country, evidence_url, verified_on`.
  - Each domain must be a registrable domain.
  - Ownership must be evidenced by an authoritative registry or directory, such
    as a national government domain registry or an accredited-institution list.
  - Cover several sectors (for example government, education, health, finance,
    transport/utilities, non-profit) and more than one country.
  - Freeze the list before querying the index.
- [ ] Run `preflight --official-domains …` first. Any allow-listed domain already
  seen in historical data (for example a domain in the Tranco training prefix)
  would be removed in cleaning, so replace it before collection.
- [ ] Fix `max_per_domain` and the converter seed in `test_sources.json` before
  collection. Full URLs, including paths and query strings, are kept. The report
  shows the class balance; review the homepage-versus-path mix in the converted
  file before the final run.
- [ ] `observed_at` = Common Crawl capture timestamp (all after the cutoff).

### Storage

- Raw downloads go in `ml_model/data/final/` (Git-ignored) or
  `ml_model/data/external/` (Git-ignored). The model artifact stays Git-ignored.
- Commit only the protocol, the source metadata (with checksums), and, after the
  single final run, the report.

## 7. Commands (PowerShell, from `backend`)

```powershell
cd C:\Users\willa\Documents\PhishGuard\backend
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Before collection (no test data needed):

```powershell
.\venv\Scripts\python.exe -m app.ml.final_evaluation preflight --official-domains ..\ml_model\final_evaluation\official_domains.csv
```

After collection is authorized, convert the downloads:

```powershell
.\venv\Scripts\python.exe -m app.ml.final_evaluation convert-phishtank --input ..\ml_model\data\final\raw\online-valid.csv --output ..\ml_model\data\final\phishing.csv
```

```powershell
.\venv\Scripts\python.exe -m app.ml.final_evaluation convert-common-crawl --index (Get-ChildItem ..\ml_model\data\final\raw\cc-index\*.jsonl).FullName --official-domains ..\ml_model\final_evaluation\official_domains.csv --phishing-feed ..\ml_model\data\final\raw\online-valid.csv --max-per-domain <N> --seed <S> --output ..\ml_model\data\final\legitimate.csv
```

Validate the inputs (format and provenance only; no predictions):

```powershell
.\venv\Scripts\python.exe -m app.ml.final_evaluation validate --dataset ..\ml_model\data\final\phishing.csv ..\ml_model\data\final\legitimate.csv
```

The single final run (after `preflight` reports `"ready_for_final_run": true`):

```powershell
.\venv\Scripts\python.exe -m app.ml.final_evaluation run --final --dataset ..\ml_model\data\final\phishing.csv ..\ml_model\data\final\legitimate.csv
```

The report is written to
`ml_model/artifacts/final_untouched_evaluation.json`. That path is
fixed in final mode and is never overwritten, so a second final run is refused.

Final mode refuses to run unless all of these hold:

- the protocol is approved;
- the working tree has no uncommitted tracked changes;
- the model checksum, threshold, and feature order match;
- the pinned Public Suffix List version is installed;
- every historical source is verified or has a recorded out-of-scope decision;
- every test source's metadata and raw-file checksums are recorded;
- the input files have no malformed rows.

`run --development-fixture --output <other path>` exercises the same pipeline on
synthetic or previously seen data. Its report is marked
`DEVELOPMENT FIXTURE RUN - NOT A FINAL RESULT`.

## 8. Decisions needed before collection

1. **Historical files:** supply the PhishTank snapshot (`a55aa3b2…`) and the
   legitimate archive (`3b888fbf…`), or exclusion lists derived from them.
2. **`Phishing_Legitimate_full.csv`:** this source has no URLs. Supply its
   original URL list, or record in a reviewed commit that it is out of scope. It
   trained only the earlier 15-feature model. To do so, change its manifest entry
   to `"format": "out_of_scope"` with a `"decision"`. The report then lists it as
   unchecked by decision.
3. **`_pre_raw` backup model:** an earlier raw-pipeline run (trained
   2026-08-31T14:48:41Z) left no metrics or input checksums. It is assumed to have
   used the same three input files. Confirm this, or record it as a known gap.
4. **PhishTank terms:** establish them (section 6).
5. **Allowlist, `max_per_domain`, converter seed, and the 100-row minimum per
   class:** fix them before collection.
6. **Approve the cutoff and protocol:** set `"approved": true` in
   `protocol.json` in a reviewed commit.

## 9. Test procedure

1. Loaders and cleaning steps are unit-tested on synthetic data only
   (`tests/test_final_evaluation.py`).
2. Commit the reviewed tooling, protocol, and source metadata; the report records
   the commit.
3. Open the test set once and run the frozen model with `run --final`.
4. **No tuning after opening the test set.** Do not change the threshold,
   features, cleaning rules, data selection, sampling, or model, and do not rerun
   with variations. Any later change requires new data collected after a new
   cutoff.

## 10. Report contents

`final_untouched_evaluation.json` contains:

- **Metrics:**
  - confusion matrix in `[[TN, FP], [FN, TP]]` order (phishing positive), with
    TN, FP, FN, and TP stated explicitly;
  - accuracy;
  - precision, recall, F1, and support for each class;
  - ROC-AUC;
  - PR-AUC, computed as average precision: the sum over descending score
    thresholds of `(R_n − R_{n−1}) × P_n`. This is step-wise, with no
    trapezoidal interpolation.
- **Fixed values:** model SHA-256, feature list in order, threshold, cutoff,
  seed, sampling method, protocol checksum, evaluation-code commit, and the
  Public Suffix List version.
- **Inputs:** checksums of the input files, raw downloads, historical manifest,
  and source metadata, plus each test source's metadata.
- **Historical overlap:** the status of each historical source, the sources that
  were checked, and any out-of-scope decisions.
- **Cleaning:** removals at every step by class and source, and template-leakage
  counts.
- **Breakdown:** class balance after cleaning and as evaluated, and performance
  by source and by observation week.
- **Limitations:**
  - accuracy, class precision, and PR-AUC depend on the test set's class
    composition (a random ranking scores PR-AUC equal to the phishing share);
  - lexical-only scope;
  - concept drift;
  - source coverage;
  - label noise.

Report the result whether it is strong or weak. Earlier results must not be
substituted for it.
