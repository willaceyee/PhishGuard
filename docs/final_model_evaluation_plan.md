# Final Untouched Model-Evaluation Plan

Status: **protocol approved on 2026-11-22; ready for data collection.** No final
test data has been collected or opened. "Model evaluation" remains unchecked in
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

## Approved evaluation rules (2026-11-22)

| Rule | Proposal |
| --- | --- |
| Model tested | The current 18-feature Random Forest only (`phishguard_url_model.joblib`, SHA-256 `ac1dc5aa…5cef9edc`, threshold 0.5). The earlier 15-feature model is not assessed. |
| Cutoff | `2026-09-01T00:00:00Z`. The newest earlier data point is a PhishTank verification at 2026-08-31T02:02:21Z, and the last earlier run finished at 2026-08-31T14:53:06Z. Only URLs verified or observed **after** the cutoff count. |
| Phishing source | PhishTank's verified-online file (`online-valid.csv`), one snapshot; each URL's date is its PhishTank verification time. |
| Legitimate source and label check | Common Crawl October 2026 crawl (`CC-MAIN-2026-43`, crawled 5–18 October 2026). A URL counts as legitimate only if its site is on a frozen list of official organization domains backed by an authoritative registry, the page returned HTTP 200 HTML, it has no login details, IP address, or unusual port in the URL, and its domain never appears in the phishing snapshot. A crawl date or a working page alone is not enough. |
| Target size | Up to **1,000 URLs per class** after cleaning (equal numbers of each). The run stops if either class has fewer than **500**. |
| Maximum per domain | **20 URLs per registrable domain** in each class (the converter collects up to 50 legitimate URLs per domain as headroom for duplicate removal). This stops one website or one phishing campaign from dominating the result and forces at least 50 different domains per class at full size. |
| Overlap with old data | Before any prediction: remove exact and near-duplicate URLs; remove any URL, or any URL whose registrable domain, appears in the PhishTank snapshot, the legitimate archive, or the 36,966 Tranco homepages used in training; then remove URLs given both labels. Every removal is counted. |
| Permissions still to verify | PhishTank's terms for academic use and publication (not stated on its developer page). Common Crawl's terms are recorded but do not specifically address republishing URL lists. Each official domain's ownership evidence. Until settled, URL lists are not published; only aggregate results are reported. |

### What approval means

Approving sets `"approved": true` in `protocol.json` in a reviewed commit. It fixes the
model, cutoff, sources, label rule, cleaning rules, seed, class sizes, and per-domain
cap above **before** any final data is downloaded, so none of them can be adjusted
after seeing results.

After approval: (1) you compile and freeze the official-domain list and run
`preflight --official-domains` to replace any domain already seen in old data;
(2) download one PhishTank snapshot and the Common Crawl index records, recording
download times, checksums, and terms in `test_sources.json`; (3) convert and
`validate` the files; (4) commit the metadata; (5) run `run --final` exactly once.
The report is written once and is never overwritten. If anything in the rules must
change after the test data is opened, the result is discarded and the process
restarts with new data collected after a new cutoff.

## 2. Cutoff

**Approved: `2026-09-01T00:00:00Z`.**

- The recovered PhishTank snapshot's latest `verification_time` is
  **2026-08-31T02:02:21Z**. The raw-pipeline run was generated at
  2026-08-31T14:53:06Z and the baseline run at 2026-08-31T06:02:06Z; the Tranco
  archive entry is dated 2026-08-30. The cutoff is later than all of them.
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
6. **Per-domain cap.** At most 20 rows per class and registrable domain are kept,
   chosen by the lowest SHA-256 of `42:<normalized URL>` (deterministic).
7. **Balanced sampling.** Each class is sorted by normalized URL, then
   `min(n_legitimate, n_phishing, 1000)` rows are drawn from each with
   `random.Random(42).sample`. The run fails if either class is empty, or below
   the protocol minimum (500 rows per class), after cleaning.

## 5. Historical sources (overlap exclusion)

Listed in
[`ml_model/final_evaluation/historical_sources.json`](../ml_model/final_evaluation/historical_sources.json).
Each raw file is verified against the SHA-256 recorded in the earlier metrics.
Final mode refuses to run unless every source is verified or excluded by a scope
decision that is also recorded in `protocol.json`. Raw files stay outside Git in
`ml_model/data/external/`.

| Source | Used by | Status (2026-11-22) |
| --- | --- | --- |
| PhishTank snapshot `a55aa3b2…52240` (recovered from `verified_online.csv`) | Baseline (B) and raw training, validation, diagnostic (C) | **Verified**: 73,945 rows, latest verification 2026-08-31T02:02:21Z |
| Legitimate `url,status` archive `3b888fbf…390ce` (recovered from `new_data_urls.csv.zip`) | B and C | **Verified**: 822,010 rows |
| `tranco_5674N.zip` `6ef97b32…a24e4` | C | **Verified**: the 36,966 homepages used in training, rebuilt exactly |
| `Phishing_Legitimate_full.csv` `204c226d…a8900` | A (earlier 15-feature model only) | **Out of scope (proposed)**: no URL column; see section 5.2 |
| Synthetic demo fixture | Pipeline fixture and tests | Verified (regenerated deterministically) |

Each historical file is checked in full (all rows, regardless of status or
verified/online flags), except Tranco, where only the homepages
`app.ml.retrain_raw` actually drew are checked; excluding the whole top-1M list
would remove nearly every official domain. Rows that cannot be parsed as URLs
(7 PhishTank, 1,866 archive) were confirmed not to have been usable for training.

`Downloads\Phishing.csv` (SHA-256 `99c732ba…`) was offered as the PhishTank file
but is a different, feature-only dataset not referenced by any recorded result; it
is not used.

### 5.1 Reconstruction evidence

The training, validation, and diagnostic URL sets were rebuilt with
`app.ml.retrain_raw` (same dates and seed 42) from the recovered files, and the
frozen model was scored on validation and diagnostic. All **23** recorded values
in `raw_training_metrics.json` were reproduced exactly
([`historical_reconstruction_evidence.json`](../ml_model/final_evaluation/historical_reconstruction_evidence.json)):

| Item | Rebuilt = recorded |
| --- | --- |
| Source checksums (PhishTank, archive, Tranco) | all three match |
| Rejected rows | PhishTank 12, archive 235 |
| Training rows | 136,550 (68,275 phishing; 34,137 archive + 34,138 Tranco legitimate) |
| Validation (9,138 rows) | `[[4302, 267], [837, 3732]]`, accuracy 0.879186, ROC-AUC 0.955051, PR-AUC 0.959678, full per-class report |
| Diagnostic (2,172 rows) | `[[1028, 58], [226, 860]]`, accuracy 0.869245, ROC-AUC 0.952746, PR-AUC 0.957893, full per-class report |

**What this shows.** It is strong supporting evidence that the rebuilt sets are
the sets used. ROC-AUC to six decimals depends on how the model ranks every one of
the 2,172 diagnostic and 9,138 validation URLs, so a different set of URLs is very
unlikely to reproduce all of these values together.

**What it cannot prove.** Exact row identity cannot be verified: the original run
saved no list or fingerprint of the URLs in each split, `retrain_raw.py` was only
committed on 2026-10-06 (after the 2026-08-31 run), and a trained model does not
contain its training URLs. The training split itself is not scored, so its
membership rests on matching counts and on the identical deterministic code that
produced the validation and diagnostic matches.

### 5.2 Scope: the earlier 15-feature dataset

This evaluation is defined as an assessment of the **current 18-feature model**
(`protocol.json` → `evaluation_scope`). Its historical coverage rule is: exclude
everything that trained, validated, diagnosed, or baseline-tested this model or
its direct raw-pipeline predecessor.

`Phishing_Legitimate_full.csv` falls outside that rule: it contains only
precomputed feature columns and trained and tested only the earlier 15-feature
model. The reconstruction above confirms the current model's 136,550 training rows
all came from the three verified raw sources. It is therefore proposed as **out of
scope**, recorded in both `protocol.json` (with its reason) and the manifest. The
tool accepts the exclusion only when both agree, and the report states it.

**Remaining limitation.** The dataset's URLs cannot be recovered, so overlap
between the final test and that dataset is unknown. This cannot leak into the
current model's training, but the report's disjointness statement names this
source as unchecked, and the result says nothing about the earlier model. The
earlier dataset also shaped early feature design (the first 15 features), which is
a design influence rather than data overlap.

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
- [ ] Converter settings proposed in `test_sources.json`: `max_per_domain` 50 and
  seed 42, fixed on approval. The evaluator then keeps at most 20 per domain, so
  the allowlist needs at least 50 usable domains (aim for 60 or more across six or
  more sectors). Full URLs, including paths and query strings, are kept. The report
  shows the class balance; review the homepage-versus-path mix in the converted
  file before the final run.
- [ ] `observed_at` = Common Crawl capture timestamp (all after the cutoff).

### Storage

- Raw downloads go in `ml_model/data/final/` (Git-ignored) or
  `ml_model/data/external/` (Git-ignored). The model artifact stays Git-ignored.
- Commit only the protocol, the source metadata (with checksums), and, after the
  single final run, the report.

### 6.1 Official-domain list (prepared 2026-11-22)

[`official_domains.csv`](../ml_model/final_evaluation/official_domains.csv) holds
**120 domains: 20 in each of the six sectors**, from two countries (68 US, 52 AU).
It was produced by
[`select_official_domains.py`](../ml_model/final_evaluation/select_official_domains.py),
which selects by fixed rules rather than by hand:

1. Filter each registry to the sector.
2. Reduce each website to its registrable domain.
3. Drop domains shared by several organizations and shared platforms (for example
   social-media pages).
4. Drop every domain already in the historical data.
5. Order the rest by SHA-256 of `42:<sector>:<domain>` and keep 20 per sector.

| Registry (ownership evidence) | Snapshot SHA-256 | Used for |
| --- | --- | --- |
| US `.gov` registry, CISA [`dotgov-data` `current-full.csv`](https://github.com/cisagov/dotgov-data/blob/fcdb786528f1a612295565ebd85ee56767ae5e65/current-full.csv), commit `fcdb7865` | `aa5f1a63…c6b3d44` | Government (state), transport and utilities (DOT and special districts), US health (HHS and health districts), US education (school districts) |
| FDIC BankFind institutions API, index `institutions_20261120100008`, active banks with $1–50 billion assets | `474c3709…e43980` | Finance; each row links to the bank's own FDIC record |
| ACNC Register of Australian charities (data.gov.au, updated 2026-11-15), Large charities | `559c2924…fef328d` | Australian education (`.edu.au` schools), health, and non-profit |

| Sector | Domains | Countries |
| --- | --- | --- |
| Government | 20 | US 20 |
| Education | 20 | AU 18, US 2 |
| Health | 20 | AU 14, US 6 |
| Finance | 20 | US 20 |
| Transport and utilities | 20 | US 20 |
| Non-profit | 20 | AU 20 |

**Checks (2026-11-22).**

- `preflight --official-domains` read all 120 domains and found **none** in the
  historical data.
- All 48 `.gov` domains are present in the pinned registry file.
- All 20 banks were re-checked live at the FDIC: each record is active and states
  the listed domain.
- All 52 Australian domains match the website in the ACNC register, by ABN.

Registry snapshots are kept outside Git in `ml_model/data/final/registry/`.

**Where evidence is hard to obtain.**

- **US non-profits:** the IRS register of tax-exempt organizations does not list
  websites. Non-profits therefore come from Australia's ACNC, which does.
- **US education:** the `.edu` registry publishes no ownership list, so US education
  is limited to school districts on `.gov` (79 exist). Most education domains are
  Australian schools on `.edu.au`.
- **Health:** US hospital registers do not record official websites. Health
  domains are federal health agencies, local health districts on `.gov`, and
  Australian health and aged-care charities, rather than large hospitals.
- **Transport:** the registry contains few transport agencies, so this sector is
  mostly water and utility districts.

**Known biases.** 48 of the 120 domains end in `.gov`, and many organizations are
small. The legitimate class is therefore less varied than general web browsing.
The report should state this.

**Feasibility of 1,000 legitimate URLs.**

- The list can supply at most 120 × 20 = 2,400 URLs after the per-domain cap.
- Reaching 1,000 needs at least 50 domains that each yield 20 usable pages in the
  October crawl after cleaning.
- That is plausible but cannot be confirmed without querying the crawl, which is
  part of collection. Small sites may have few captured pages.
- The converter's summary (`rows`, `domains_with_rows`) shows the yield before the
  final run. If fewer than 1,000 survive, the approved rules sample the smaller
  number, down to the 500 minimum, and the report states the achieved size.

### 6.2 PhishTank terms (checked 2026-11-22)

| Source | What it says |
| --- | --- |
| [FAQ](https://phishtank.org/faq.php) | PhishTank is free to everyone, website and data. Commercial and non-commercial use of the **API** is allowed. The data is shared on the website and through the API. PhishTank is operated by Cisco Talos Intelligence Group. |
| [Home page](https://phishtank.org/) | Offers an open API for developers and researchers at no charge. |
| [Developer information](https://phishtank.org/developer_info.php) | Bulk files are updated hourly. Register for an application key for automated downloads; without one, only a few downloads per day are allowed. A descriptive User-Agent is required, recommended format `phishtank/<username>`. |
| [API information](https://phishtank.org/api_info.php) | Rate limits apply (HTTP 509 when exceeded). Heavy users should download a local copy instead. |
| Footer "Terms of Use" link ([Cisco General Terms](https://www.cisco.com/c/en/us/about/legal/cloud-and-software/end_user_license_agreement.html)) | A general licence for Cisco products. The 8-page text never mentions PhishTank or Talos, and has no clauses on data attribution, research use, or redistribution. |

**Resolved.** Free use for research is allowed; the FAQ and the home page state it.

**Unresolved.**

- No attribution requirement is stated. As good practice, cite PhishTank (operated
  by Cisco Talos) as the source.
- Redistribution of the downloaded URL list is not addressed. Until PhishTank
  confirms otherwise, publish only aggregate results and checksums, not the URLs.
- The free-use statements name the API explicitly. Bulk files are offered on the
  developer page with no separate licence.

Optional confirmation: [PhishTank contact page](https://www.phishtank.com/contact.php).

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
.\venv\Scripts\python.exe -m app.ml.final_evaluation convert-common-crawl --index (Get-ChildItem ..\ml_model\data\final\raw\cc-index\*.jsonl).FullName --official-domains ..\ml_model\final_evaluation\official_domains.csv --phishing-feed ..\ml_model\data\final\raw\online-valid.csv --max-per-domain 50 --seed 42 --output ..\ml_model\data\final\legitimate.csv
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

1. ~~Historical files~~: recovered and verified (section 5).
2. **Scope of the older dataset:** approve or reject the out-of-scope proposal for
   `Phishing_Legitimate_full.csv` (section 5.2).
3. **`_pre_raw` backup model:** an earlier raw-pipeline run (trained
   2026-08-31T14:48:41Z) left no metrics or input checksums. It is assumed to have
   used the same inputs; it is not the model being evaluated.
4. ~~Permissions~~: PhishTank terms checked and domain ownership evidence recorded
   (sections 6.1-6.2). Redistribution of PhishTank URL lists remains unconfirmed,
   so only aggregate results are published.
5. **Approve the rules** in "Proposed evaluation rules" (cutoff, sources, label
   rule, 1,000/500 class sizes, 20 per domain) by setting `"approved": true` in
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
