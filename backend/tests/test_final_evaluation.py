import csv
import json
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import pytest

from app.ml import final_evaluation as fe
from app.ml.evaluate import classification_metrics, sha256
from app.ml.prepare_demo_data import write_demo_dataset
from app.ml.retrain_raw import load_tranco_pool
from app.ml.service import load_bundle
from app.ml.train import train_model


CUTOFF = "2026-09-01T00:00:00Z"
NOW = datetime(2026, 11, 22, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def model_path(tmp_path_factory):
    directory = tmp_path_factory.mktemp("final-model")
    dataset = directory / "urls.csv"
    path = directory / "model.joblib"
    write_demo_dataset(dataset, samples_per_class=40)
    train_model(dataset, path, directory / "metrics.json")
    load_bundle.cache_clear()
    return path


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def write_zip(path, name, text):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, text)
    return path


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def protocol(tmp_path, model, approved=True, minimum=1):
    bundle = load_bundle(str(model))
    return write_json(tmp_path / "protocol.json", {
        "format": "phishguard-final-evaluation-protocol/1",
        "approved": approved,
        "cutoff_utc": CUTOFF,
        "model": {"path": str(model), "sha256": sha256(model), "threshold": 0.5,
                  "feature_names": list(bundle["feature_names"])},
        "sampling": {"method": "balanced_downsample", "seed": 42, "minimum_rows_per_class": minimum},
        "public_suffix_list": {"package": "publicsuffixlist", "version": metadata.version("publicsuffixlist")},
    })


def manifest(tmp_path, extra_sources=(), name="manifest.json"):
    history = write_csv(tmp_path / "hist_phish.csv", ["url", "verified", "verification_time", "online"], [
        ["http://login.old-bank.example.co.uk/verify", "yes", "2026-07-01T00:00:00+00:00", "yes"],
        ["http://seen-exact.example.net/reset?id=1", "yes", "2026-07-02T00:00:00+00:00", "yes"],
    ])
    legit = write_zip(tmp_path / "hist_legit.zip", "urls.csv", "url,status\nwww.oldsite.org/home,1\n")
    sources = [
        {"name": "hist_phish", "format": "phishtank_csv", "path": str(history), "sha256": sha256(history)},
        {"name": "hist_legit", "format": "url_csv_zip", "path": str(legit), "sha256": sha256(legit)},
        *extra_sources,
    ]
    return write_json(tmp_path / name, {"format": "phishguard-historical-sources/1", "sources": sources})


def source_metadata(tmp_path, complete=True):
    raw = tmp_path / "raw_download.txt"
    raw.write_text("raw", encoding="utf-8")
    base = {
        "publisher": "p", "access_url": "u", "documentation_url": "d", "snapshot_downloaded_at_utc": "2026-11-23T00:00:00Z",
        "terms": "t", "label_definition": "l", "timestamp_field": "f", "sampling_rule": "s", "coverage_notes": "c",
        "raw_files": [{"path": str(raw), "sha256": sha256(raw)}],
    }
    sources = {"feed": {**base, "label": "phishing"}, "official": {**base, "label": "legitimate"}}
    if not complete:
        sources["feed"]["terms"] = None
    return write_json(tmp_path / ("sources.json" if complete else "sources_incomplete.json"), {"format": "phishguard-final-test-sources/1", "sources": sources})


def dataset(tmp_path, rows, name="test.csv"):
    return write_csv(tmp_path / name, ["url", "label", "source", "observed_at"], rows)


def fixture_rows(count=12):
    rows = []
    for index in range(count):
        rows.append([f"https://www.agency{index}.gov.example/services/permits", "legitimate", "official", "2026-10-06T10:00:00Z"])
        rows.append([f"http://secure-{index}.phish{index}.test/account/verify-login", "phishing", "feed", "2026-10-07T10:00:00Z"])
    return rows


# --------------------------------------------------------------------------- URL rules


def test_normalization_rules():
    normalized, host = fe.normalize_url("HTTPS://User@WWW.Example.COM.:443/a/b/%2f/?q=1#frag")
    assert normalized == "https://User@www.example.com/a/b/%2F?q=1"
    assert host == "www.example.com"
    assert fe.normalize_url("http://example.com")[0] == "http://example.com/"
    assert fe.normalize_url("http://example.com:8080/x/")[0] == "http://example.com:8080/x"
    assert fe.normalize_url("example.com/x", require_scheme=False)[0] == "http://example.com/x"
    for bad in ("example.com/x", "ftp://example.com/", "http://exa mple.com/", "", "http://example.com:99999/"):
        with pytest.raises(ValueError):
            fe.normalize_url(bad)


def test_registrable_domain_handles_multi_part_and_private_suffixes():
    assert fe.registrable_domain("a.b.example.co.uk") == "example.co.uk"
    assert fe.registrable_domain("www.example.co.uk") == "example.co.uk"
    assert fe.registrable_domain("co.uk") == "co.uk"
    assert fe.registrable_domain("tenant.github.io") == "tenant.github.io"
    assert fe.registrable_domain("192.0.2.1") == "192.0.2.1"
    assert fe.url_keys("http://[2001:db8::1]/x").domain == "2001:db8::1"


def test_near_duplicate_template_rule():
    template = lambda url: fe.url_keys(url).template  # noqa: E731
    assert template("https://www.a.com/u/12345/view?id=1&b=2") == template("https://a.com/u/987/view?b=9&id=7")
    assert template("https://a.com/r/3f2a9c81bd/x") == template("https://a.com/r/a1b2c3d4e5f6/x")
    assert template("https://a.com/t/550e8400-e29b-41d4-a716-446655440000") == "a.com/t/{uuid}?"
    assert template("https://a.com/s/Ab3dEf9hIj2kLm7n") == "a.com/s/{token}?"
    assert template("https://a.com/invoice-48213") == template("https://a.com/invoice-99")
    assert template("https://a.com/v1/x") != template("https://a.com/v2/x")
    assert template("https://a.com/x?id=1") != template("https://a.com/x?ref=1")


def test_timestamps_require_utc_offset():
    assert fe.parse_utc("2026-10-01T12:00:00Z") == datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert fe.parse_utc("2026-10-01T14:00:00+02:00") == datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    for bad in ("2026-10-01T12:00:00", "2026-10-01", "01/10/2026 12:00", "", None):
        with pytest.raises(ValueError):
            fe.parse_utc(bad)


# --------------------------------------------------------------------------- input validation


def test_cutoff_boundary_and_malformed_rows(tmp_path):
    path = dataset(tmp_path, [
        ["https://a.example.org/x", "legitimate", "official", CUTOFF],
        ["https://b.example.org/x", "legitimate", "official", "2026-09-01T00:00:01Z"],
        ["https://c.example.org/x", "Phishing", "feed", "2026-10-01T00:00:00Z"],
        ["https://d.example.org/x", "1", "feed", "2026-10-01T00:00:00Z"],
        ["https://e.example.org/x", "phishing", "feed", "2026-10-01 00:00:00"],
        ["https://f.example.org/x", "phishing", "feed", "2026-10-01T00:00:00"],
        ["f.example.org/no-scheme", "phishing", "feed", "2026-10-01T00:00:00Z"],
        ["https://g.example.org/x", "phishing", "", "2026-10-01T00:00:00Z"],
        ["https://h.example.org/x", "phishing", "feed", "2027-01-01T00:00:00Z"],
        ["https://" + "a" * 2100 + ".org/", "phishing", "feed", "2026-10-01T00:00:00Z"],
    ])
    rows, early, errors = fe.read_dataset(path, fe.parse_utc(CUTOFF), NOW)
    assert [row.line for row in early] == [2]
    assert [row.line for row in rows] == [3]
    assert [line for line, _ in errors] == [4, 5, 6, 7, 8, 9, 10, 11]
    assert "exactly 'phishing' or 'legitimate'" in errors[0][1]
    assert "future" in errors[6][1]


def test_missing_columns_are_rejected(tmp_path):
    path = write_csv(tmp_path / "bad.csv", ["url", "label", "observed_at"], [])
    with pytest.raises(fe.FinalEvaluationError, match="source"):
        fe.read_dataset(path, fe.parse_utc(CUTOFF), NOW)


# --------------------------------------------------------------------------- cleaning


def clean(tmp_path, rows, extra_sources=()):
    index = fe.load_historical_index(manifest(tmp_path, extra_sources))
    parsed, early, errors = fe.read_dataset(dataset(tmp_path, rows), fe.parse_utc(CUTOFF), NOW)
    return fe.clean_dataset(parsed, early, errors, index)


def step(steps, name):
    return next(item for item in steps if item["step"] == name)


def test_cleaning_steps_are_counted_in_order(tmp_path):
    rows = [
        ["https://keep.example.org/a", "legitimate", "official", "2026-10-02T00:00:00Z"],
        ["HTTPS://KEEP.example.org/a/#x", "legitimate", "official", "2026-10-03T00:00:00Z"],  # exact dup
        ["http://p.bad.test/u/1001/login", "phishing", "feed", "2026-10-02T00:00:00Z"],
        ["http://p.bad.test/u/2002/login", "phishing", "feed", "2026-10-01T00:00:00Z"],  # near dup (kept: earlier)
        ["http://seen-exact.example.net/reset?id=1", "phishing", "feed", "2026-10-01T00:00:00Z"],  # URL overlap
        ["http://other.old-bank.example.co.uk/pay", "phishing", "feed", "2026-10-01T00:00:00Z"],  # domain overlap
        ["http://old-bank-example.co.uk/pay", "phishing", "feed", "2026-10-01T00:00:00Z"],  # different domain, kept
        ["https://oldsite.org/new-page", "legitimate", "official", "2026-10-01T00:00:00Z"],  # domain overlap (scheme-less history)
        ["https://shared.example.org/x", "legitimate", "official", "2026-10-01T00:00:00Z"],  # conflict
        ["https://shared.example.org/x", "phishing", "feed", "2026-10-01T00:00:00Z"],  # conflict
        ["https://early.example.org/", "legitimate", "official", "2026-08-31T23:59:59Z"],  # before cutoff
    ]
    cleaned, steps, leakage = clean(tmp_path, rows)
    assert step(steps, "removed_at_or_before_cutoff")["removed"]["total"] == 1
    assert step(steps, "exact_duplicates_after_normalization")["removed"]["by_class"] == {"legitimate": 1, "phishing": 0}
    near = step(steps, "near_duplicates_by_template")
    assert near["removed"]["by_source"] == {"feed": {"phishing": 1}}
    url_step = step(steps, "historical_normalized_url_overlap")
    assert url_step["removed"]["total"] == 1 and url_step["matched_sources"] == {"hist_phish": 1}
    domain_step = step(steps, "historical_registrable_domain_overlap")
    assert domain_step["removed"]["total"] == 2
    assert domain_step["matched_sources"] == {"hist_phish": 1, "hist_legit": 1}
    conflict = step(steps, "conflicting_labels")
    assert conflict["conflicting_normalized_urls"] == 1 and conflict["removed"]["total"] == 2
    kept = sorted(row.keys.normalized for row in cleaned)
    assert kept == ["http://old-bank-example.co.uk/pay", "http://p.bad.test/u/2002/login", "https://keep.example.org/a"]
    assert leakage["before_overlap_removal"]["sharing_host_with_history"] >= 1
    assert leakage["after_cleaning"]["sharing_host_with_history"] == 0


def test_conflict_hidden_behind_near_duplicate_is_removed(tmp_path):
    rows = [
        ["http://x.test/item/111", "phishing", "feed", "2026-10-01T00:00:00Z"],
        ["http://x.test/item/222", "phishing", "feed", "2026-10-02T00:00:00Z"],  # near dup of 111
        ["http://x.test/item/222", "legitimate", "official", "2026-10-02T00:00:00Z"],  # conflicts with dropped dup
    ]
    cleaned, steps, _ = clean(tmp_path, rows)
    assert step(steps, "conflicting_labels")["removed"]["total"] == 2
    assert cleaned == []


def test_empty_class_or_minimum_fails(tmp_path):
    cleaned, _, _ = clean(tmp_path, [["https://only.example.org/a", "legitimate", "official", "2026-10-01T00:00:00Z"]])
    with pytest.raises(fe.FinalEvaluationError, match="No phishing rows remain"):
        fe.sample_balanced(cleaned, 42, 1)
    cleaned, _, _ = clean(tmp_path, fixture_rows(3))
    with pytest.raises(fe.FinalEvaluationError, match="requires 10"):
        fe.sample_balanced(cleaned, 42, 10)
    sample, size = fe.sample_balanced(cleaned, 42, 1)
    assert size == 3 and len(sample) == 6
    assert [row.line for row in sample] == [row.line for row in fe.sample_balanced(cleaned, 42, 1)[0]]


# --------------------------------------------------------------------------- historical sources


def test_historical_source_statuses(tmp_path):
    present = write_csv(tmp_path / "h.csv", ["url"], [["http://a.example/"]])
    index = fe.load_historical_index(write_json(tmp_path / "m.json", {
        "format": "phishguard-historical-sources/1",
        "sources": [
            {"name": "missing", "format": "phishtank_csv", "path": str(tmp_path / "nope.csv"), "sha256": "0"},
            {"name": "mismatch", "format": "phishtank_csv", "path": str(present), "sha256": "0"},
            {"name": "features_only", "format": "no_urls", "sha256": "0"},
            {"name": "undecided", "format": "out_of_scope"},
            {"name": "decided", "format": "out_of_scope", "decision": "Different model; reviewed 2026-11-30."},
            {"name": "demo", "format": "synthetic_demo_generator", "samples_per_class": 5, "seed": 42},
        ],
    }))
    status = {source.name: source.status for source in index.sources}
    assert status == {"missing": "missing", "mismatch": "checksum_mismatch", "features_only": "gap",
                      "undecided": "gap", "decided": "out_of_scope", "demo": "verified"}
    assert [source.name for source in index.gaps] == ["missing", "mismatch", "features_only", "undecided"]
    with pytest.raises(fe.FinalEvaluationError, match="Unknown historical source format"):
        fe.load_historical_source({"name": "x", "format": "mystery", "path": str(present), "sha256": sha256(present)}, {})


def test_exclusion_list_round_trip_and_checksum(tmp_path):
    manifest_path = manifest(tmp_path)
    out = tmp_path / "excl" / "hist_phish.json"
    built = fe.build_exclusion_list(manifest_path, "hist_phish", out)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = data["sources"][0]
    raw = Path(entry["path"])
    raw.rename(raw.with_suffix(".moved"))  # raw file no longer available
    entry["exclusion_list"] = {"path": str(out), "sha256": built["sha256"]}
    write_json(manifest_path, data)
    source = fe.load_historical_index(manifest_path).sources[0]
    assert source.status == "verified" and "exclusion list" in source.detail
    assert "example.co.uk" in source.domains and source.rows == 2
    entry["exclusion_list"]["sha256"] = "0" * 64
    write_json(manifest_path, data)
    with pytest.raises(fe.FinalEvaluationError, match="Exclusion list"):
        fe.load_historical_index(manifest_path)
    entry["exclusion_list"]["sha256"] = built["sha256"]
    entry["sha256"] = "1" * 64
    write_json(manifest_path, data)
    with pytest.raises(fe.FinalEvaluationError, match="not derived"):
        fe.load_historical_index(manifest_path)
    with pytest.raises(fe.FinalEvaluationError, match="Cannot build"):
        fe.build_exclusion_list(manifest_path, "hist_phish", tmp_path / "again.json")


def tranco_fixture(tmp_path):
    phish = write_csv(tmp_path / "pt.csv", ["url", "verified", "verification_time", "online"], [
        ["https://site1.org/", "yes", "2026-07-01T00:00:00+00:00", "yes"],  # also a Tranco homepage: skipped
        ["http://p2.test/a", "yes", "2026-07-02T00:00:00+00:00", "yes"],
        ["http://p3.test/a", "yes", "2026-08-05T00:00:00+00:00", "yes"],
        ["http://p4.test/a", "yes", "2026-08-25T00:00:00+00:00", "yes"],
    ])
    lines = "\n".join(f"{rank},site{rank}.org" for rank in range(1, 11))
    tranco = write_zip(tmp_path / "tranco.zip", "top-1m.csv", lines)
    return phish, tranco


def test_tranco_reconstruction_matches_training_pipeline(tmp_path):
    phish, tranco = tranco_fixture(tmp_path)
    entry = {
        "name": "tranco", "format": "tranco_used_homepages", "path": str(tranco), "sha256": sha256(tranco),
        "phishing_source": "pt", "train_end": "2026-08-01T00:00:00Z", "diagnostic_start": "2026-08-22T00:00:00Z",
        "expected_phishing_rows": {"train": 2, "validation": 1, "diagnostic": 1},
        "expected_homepages": {"train": 1, "validation": 1, "diagnostic": 1},
    }
    by_name = {"pt": {"name": "pt", "format": "phishtank_csv", "path": str(phish), "sha256": sha256(phish)}}
    source = fe.load_historical_source(entry, by_name)
    excluded = {"https://site1.org/", "http://p2.test/a", "http://p3.test/a", "http://p4.test/a"}
    expected = load_tranco_pool(tranco, excluded)[:3]
    assert sorted(source.urls) == sorted(fe.normalize_url(url)[0] for url in expected)
    assert source.domains == {"site2.org", "site3.org", "site4.org"}  # rank 1 skipped: its homepage is in the phishing data
    with pytest.raises(fe.FinalEvaluationError, match="do not match the recorded training run"):
        fe.load_historical_source({**entry, "expected_phishing_rows": {"train": 9}}, by_name)
    with pytest.raises(fe.FinalEvaluationError, match="differ from"):
        fe.load_historical_source({**entry, "expected_homepages": {"train": 9, "validation": 1, "diagnostic": 1}}, by_name)
    by_name["pt"]["sha256"] = "0"
    assert fe.load_historical_source(entry, by_name).status == "missing"
    with pytest.raises(fe.FinalEvaluationError, match="yielded"):
        fe.used_tranco_homepages(tranco, set(), 50)


# --------------------------------------------------------------------------- end-to-end runs


def test_development_run_writes_full_report(tmp_path, model_path):
    output = tmp_path / "dev_report.json"
    report = fe.run_evaluation(
        dataset(tmp_path, fixture_rows()), output, final=False,
        protocol_path=protocol(tmp_path, model_path, approved=False),
        manifest_path=manifest(tmp_path, [{"name": "gap", "format": "no_urls"}], "gap.json"),
        sources_path=source_metadata(tmp_path, complete=False), now=NOW,
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["report_type"].startswith("DEVELOPMENT FIXTURE RUN")
    assert report["model"]["sha256"] == sha256(model_path)
    assert report["protocol"]["cutoff_utc"] == CUTOFF and report["protocol"]["random_seed"] == 42
    assert report["overlap_check"]["statement"].startswith("NOT fully checked")
    assert report["test_source_problems"] == ["feed: 'terms' is not recorded"]
    metrics = report["metrics"]
    (tn, fp), (fn, tp) = metrics["confusion_matrix"]
    assert (tn, fp, fn, tp) == (metrics["true_negatives"], metrics["false_positives"],
                                metrics["false_negatives"], metrics["true_positives"])
    assert tn + fp + fn + tp == 24
    assert set(metrics["per_class"]) == {"legitimate", "phishing"}
    assert "step-wise" in metrics["pr_auc_method"]
    assert report["class_balance"]["evaluated"] == {"legitimate": 12, "phishing": 12}
    assert step(report["cleaning_steps"], "balanced_sampling")["remaining"]["total"] == 24
    assert "official (legitimate)" in report["breakdown"]["by_source"]
    with pytest.raises(fe.FinalEvaluationError, match="different --output"):
        fe.run_evaluation(dataset(tmp_path, fixture_rows()), fe.DEFAULT_REPORT, final=False,
                          protocol_path=protocol(tmp_path, model_path), manifest_path=manifest(tmp_path),
                          sources_path=source_metadata(tmp_path), now=NOW)


def test_final_run_gates_and_single_run(tmp_path, model_path, monkeypatch):
    report_path = tmp_path / "artifacts" / "final.json"
    monkeypatch.setattr(fe, "DEFAULT_REPORT", report_path)
    monkeypatch.setattr(fe, "git_state", lambda: {"commit": "abc123", "tracked_changes": []})
    data = dataset(tmp_path, fixture_rows())
    kwargs = dict(manifest_path=manifest(tmp_path), sources_path=source_metadata(tmp_path), now=NOW)

    with pytest.raises(fe.FinalEvaluationError, match="not approved"):
        fe.run_evaluation(data, report_path, True, protocol(tmp_path, model_path, approved=False), **kwargs)
    approved = protocol(tmp_path, model_path)
    with pytest.raises(fe.FinalEvaluationError, match="written only to"):
        fe.run_evaluation(data, tmp_path / "elsewhere.json", True, approved, **kwargs)
    with pytest.raises(fe.FinalEvaluationError, match="cannot be fully checked"):
        fe.run_evaluation(data, report_path, True, approved, manifest_path=manifest(tmp_path, [{"name": "gap", "format": "no_urls"}], "gap.json"),
                          sources_path=kwargs["sources_path"], now=NOW)
    with pytest.raises(fe.FinalEvaluationError, match="Test-source metadata incomplete"):
        fe.run_evaluation(data, report_path, True, approved, manifest_path=kwargs["manifest_path"],
                          sources_path=source_metadata(tmp_path, complete=False), now=NOW)
    malformed = dataset(tmp_path, fixture_rows() + [["https://z.example.org/", "benign", "official", "2026-10-01T00:00:00Z"]], "bad.csv")
    with pytest.raises(fe.FinalEvaluationError, match="malformed"):
        fe.run_evaluation(malformed, report_path, True, approved, **kwargs)
    monkeypatch.setattr(fe, "git_state", lambda: {"commit": "abc123", "tracked_changes": [" M x.py"]})
    with pytest.raises(fe.FinalEvaluationError, match="uncommitted"):
        fe.run_evaluation(data, report_path, True, approved, **kwargs)
    monkeypatch.setattr(fe, "git_state", lambda: {"commit": "abc123", "tracked_changes": []})

    report = fe.run_evaluation(data, report_path, True, approved, **kwargs)
    assert report["final"] is True and report["evaluation_code"]["commit"] == "abc123"
    assert report["overlap_check"]["statement"].startswith("Disjoint")
    assert report["inputs"]["datasets"] == [{"path": str(data), "sha256": sha256(data)}]
    with pytest.raises(fe.FinalEvaluationError, match="runs once"):
        fe.run_evaluation(data, report_path, True, approved, **kwargs)


def test_model_checks_fail_closed(tmp_path, model_path):
    path = protocol(tmp_path, model_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    loaded = fe.load_protocol(path)
    assert fe.check_model(loaded)[0]["threshold"] == 0.5
    with pytest.raises(fe.FinalEvaluationError, match="not found"):
        fe.check_model(loaded, tmp_path / "absent.joblib")
    for change, message in (
        ({"sha256": "0" * 64}, "does not match"),
        ({"threshold": 0.4}, "threshold"),
        ({"feature_names": ["url_length"]}, "feature order"),
    ):
        broken = {**data, "model": {**data["model"], **change}}
        with pytest.raises(fe.FinalEvaluationError, match=message):
            fe.check_model(fe.load_protocol(write_json(tmp_path / "p2.json", broken)))
    pinned = fe.load_protocol(write_json(tmp_path / "p3.json", {**data, "public_suffix_list": {"version": "0.0.1"}}))
    with pytest.raises(fe.FinalEvaluationError, match="pins"):
        fe.check_public_suffix_version(pinned)
    with pytest.raises(fe.FinalEvaluationError, match="is not a"):
        fe.load_protocol(write_json(tmp_path / "p4.json", {"format": "other"}))


def test_source_label_and_metadata_checks(tmp_path):
    sources = source_metadata(tmp_path)
    result = fe.check_test_sources(sources, {"feed", "undeclared"}, strict=False)
    assert "source 'undeclared' is not declared in sources.json" in result["problems"]
    data = json.loads(sources.read_text(encoding="utf-8"))
    data["sources"]["feed"]["raw_files"] = [{"path": str(tmp_path / "raw_download.txt"), "sha256": "0"},
                                            {"path": str(tmp_path / "gone.txt"), "sha256": "0"}]
    data["sources"]["official"]["raw_files"] = []
    problems = fe.check_test_sources(write_json(sources, data), {"feed", "official"}, strict=False)["problems"]
    assert any("checksum differs" in p for p in problems) and any("not found" in p for p in problems)
    assert any("no raw_files" in p for p in problems)
    rows, _, _ = fe.read_dataset(dataset(tmp_path, [["https://a.example.org/", "phishing", "official", "2026-10-01T00:00:00Z"]]),
                                 fe.parse_utc(CUTOFF), NOW)
    with pytest.raises(fe.FinalEvaluationError, match="declared label"):
        fe.check_source_labels(rows, data["sources"])


def test_classification_metrics_known_values():
    metrics = classification_metrics([0, 0, 1, 1], [0.1, 0.6, 0.4, 0.9], 0.5)
    assert metrics["confusion_matrix"] == [[1, 1], [1, 1]]
    assert metrics["accuracy"] == 0.5
    assert metrics["per_class"]["phishing"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    assert metrics["roc_auc"] == 0.75 and metrics["pr_auc"] == pytest.approx(0.833333)
    assert classification_metrics([1, 1], [0.2, 0.9], 0.5)["roc_auc"] is None


# --------------------------------------------------------------------------- converters


def test_convert_phishtank(tmp_path):
    raw = write_csv(tmp_path / "online-valid.csv",
                    ["phish_id", "url", "phish_detail_url", "submission_time", "verified", "verification_time", "online", "target"], [
        ["1", "http://a.test/login", "", "2026-11-20T00:00:00+00:00", "yes", "2026-11-20T01:00:00+00:00", "yes", "Bank"],
        ["2", "http://b.test/login", "", "2026-11-20T00:00:00+00:00", "no", "2026-11-20T01:00:00+00:00", "yes", "Bank"],
        ["3", "http://c.test/login", "", "2026-11-20T00:00:00+00:00", "yes", "yesterday", "yes", "Bank"],
    ])
    out = tmp_path / "phish.csv"
    summary = fe.convert_phishtank(raw, out)
    assert summary["rows"] == 1 and summary["skipped"] == {"not_verified_online": 1, "invalid_verification_time": 1}
    rows, _, errors = fe.read_dataset(out, fe.parse_utc(CUTOFF), NOW)
    assert errors == [] and rows[0].observed_at == datetime(2026, 11, 20, 1, tzinfo=timezone.utc)
    with pytest.raises(fe.FinalEvaluationError, match="must contain"):
        fe.convert_phishtank(write_csv(tmp_path / "x.csv", ["url"], []), out)


def test_convert_common_crawl_applies_benign_label_rule(tmp_path):
    domains = write_csv(tmp_path / "official.csv", list(fe.OFFICIAL_DOMAIN_COLUMNS), [
        ["agency.gov.uk", "Agency", "government", "GB", "https://registry.example/agency", "2026-11-01"],
        ["uni.ac.uk", "University", "education", "GB", "https://registry.example/uni", "2026-11-01"],
        ["clinic.example", "Clinic", "health", "US", "https://registry.example/clinic", "2026-11-01"],
    ])
    phishing = write_csv(tmp_path / "feed.csv", ["url"], [["http://login.clinic.example/verify"]])

    def capture(url, status="200", mime="text/html", stamp="20261010120000"):
        return json.dumps({"url": url, "timestamp": stamp, "status": status, "mime-detected": mime})

    lines = [
        capture("https://www.agency.gov.uk/services/apply?step=2"),
        capture("https://www.agency.gov.uk/services/apply?step=2", stamp="20261008000000"),  # earlier duplicate
        capture("https://forms.agency.gov.uk/start"),
        capture("https://agency.gov.uk/a"), capture("https://agency.gov.uk/b"),
        capture("https://uni.ac.uk/news", status="404"),
        capture("https://uni.ac.uk/file.pdf", mime="application/pdf"),
        capture("https://user@uni.ac.uk/x"), capture("https://uni.ac.uk:8443/x"), capture("http://192.0.2.5/x"),
        capture("https://notagency.gov.uk/x"),
        capture("https://www.clinic.example/book"),
        "not json", "",
    ]
    index = tmp_path / "cdx.jsonl"
    index.write_text("\n".join(lines), encoding="utf-8")
    out = tmp_path / "legit.csv"
    summary = fe.convert_common_crawl([index], domains, out, max_per_domain=3, seed=7, phishing_csv=phishing)
    assert summary["rows"] == 3 and summary["contested_domains_excluded"] == ["clinic.example"]
    assert summary["skipped"] == {"not_200_html": 2, "userinfo_ip_or_port": 3, "domain_not_allow_listed": 1,
                                  "domain_in_phishing_feed": 1, "unparseable_record": 1}
    rows, _, errors = fe.read_dataset(out, fe.parse_utc(CUTOFF), NOW)
    assert errors == [] and {row.keys.domain for row in rows} == {"agency.gov.uk"}
    dup = [row for row in rows if row.url.endswith("step=2")]
    assert not dup or dup[0].observed_at == datetime(2026, 10, 8, tzinfo=timezone.utc)
    again = tmp_path / "legit2.csv"
    fe.convert_common_crawl([index], domains, again, max_per_domain=3, seed=7, phishing_csv=phishing)
    assert again.read_bytes() == out.read_bytes()


def test_official_domain_list_validation(tmp_path):
    header = list(fe.OFFICIAL_DOMAIN_COLUMNS)
    with pytest.raises(fe.FinalEvaluationError, match="not a registrable domain"):
        fe.read_official_domains(write_csv(tmp_path / "a.csv", header, [["www.agency.gov.uk", "A", "g", "GB", "e", "d"]]))
    with pytest.raises(fe.FinalEvaluationError, match="every column"):
        fe.read_official_domains(write_csv(tmp_path / "b.csv", header, [["agency.gov.uk", "", "g", "GB", "e", "d"]]))
    with pytest.raises(fe.FinalEvaluationError, match="must have columns"):
        fe.read_official_domains(write_csv(tmp_path / "c.csv", ["domain"], []))


# --------------------------------------------------------------------------- CLI


def test_cli_commands(tmp_path, model_path, capsys):
    proto = protocol(tmp_path, model_path, approved=False)
    hist = manifest(tmp_path)
    common = ["--protocol", str(proto), "--historical-manifest", str(hist)]
    assert fe.main([*common, "preflight", "--official-domains", str(write_csv(
        tmp_path / "od.csv", list(fe.OFFICIAL_DOMAIN_COLUMNS), [["oldsite.org", "O", "s", "GB", "e", "d"]]))]) == 1
    result = json.loads(capsys.readouterr().out)
    assert "protocol.json is not approved" in result["blockers"]
    assert result["official_domains_seen_in_history"] == ["oldsite.org"]

    data = dataset(tmp_path, fixture_rows() + [["bad", "phishing", "feed", "2026-10-01T00:00:00Z"]])
    sources = source_metadata(tmp_path)
    assert fe.main([*common, "validate", "--dataset", str(data), "--test-sources", str(sources)]) == 1
    validated = json.loads(capsys.readouterr().out)
    assert validated["malformed_rows"] == 1 and validated["malformed_lines_first_20"] == ["test.csv:26"]
    assert "bad" not in json.dumps(validated["malformed_reasons"]).replace("invalid", "")

    rows = fixture_rows()
    legit = dataset(tmp_path, [row for row in rows if row[1] == "legitimate"], "legit.csv")
    clean_data = dataset(tmp_path, [row for row in rows if row[1] == "phishing"], "clean.csv")
    assert fe.main([*common, "run", "--development-fixture", "--dataset", str(legit), str(clean_data),
                    "--test-sources", str(sources), "--output", str(tmp_path / "r.json")]) == 0
    assert json.loads(capsys.readouterr().out)["metrics"]["rows"] == 24
    assert fe.main([*common, "run", "--final", "--dataset", str(clean_data), "--test-sources", str(sources)]) == 2
    assert "Final run refused" in capsys.readouterr().err

    assert fe.main([*common, "build-exclusions", "--source", "hist_legit", "--output", str(tmp_path / "e.json")]) == 0
    capsys.readouterr()
    raw = write_csv(tmp_path / "pt.csv", ["url", "verified", "verification_time", "online"],
                    [["http://a.test/x", "yes", "2026-11-01T00:00:00+00:00", "yes"]])
    assert fe.main(["convert-phishtank", "--input", str(raw), "--output", str(tmp_path / "pt_out.csv")]) == 0
    index = tmp_path / "i.jsonl"
    index.write_text(json.dumps({"url": "https://oldsite.org/a", "timestamp": "20261010000000", "status": "200", "mime": "text/html"}), encoding="utf-8")
    assert fe.main(["convert-common-crawl", "--index", str(index), "--official-domains", str(tmp_path / "od.csv"),
                    "--output", str(tmp_path / "cc.csv"), "--max-per-domain", "5", "--seed", "1"]) == 0


# --------------------------------------------------------------------------- scope and sampling limits


def test_scope_must_match_between_protocol_and_manifest(tmp_path, model_path, monkeypatch):
    excluded = {"name": "older_features", "format": "out_of_scope", "decision": "Trained only the earlier model."}
    index = fe.load_historical_index(manifest(tmp_path, [excluded], "scoped.json"))
    with_scope = {"evaluation_scope": {"excluded_historical_sources": [{"name": "older_features", "reason": "earlier model only"}]}}
    assert fe.check_scope(with_scope, index) == []
    assert fe.check_scope({}, index) == ["older_features is out of scope in the manifest but not excluded in protocol.json"]
    clean_index = fe.load_historical_index(manifest(tmp_path))
    assert fe.check_scope(with_scope, clean_index) == [
        "protocol.json excludes older_features, but the manifest does not mark it out of scope"]
    no_reason = {"evaluation_scope": {"excluded_historical_sources": [{"name": "older_features", "reason": " "}]}}
    assert fe.check_scope(no_reason, index) == ["protocol.json gives no reason for excluding older_features"]
    assert "Not checked, by recorded scope decision: older_features" in fe.overlap_statement(index)
    assert fe.overlap_statement(clean_index).startswith("Disjoint") and "scope" not in fe.overlap_statement(clean_index)

    report_path = tmp_path / "artifacts" / "final.json"
    monkeypatch.setattr(fe, "DEFAULT_REPORT", report_path)
    monkeypatch.setattr(fe, "git_state", lambda: {"commit": "abc123", "tracked_changes": []})
    data = dataset(tmp_path, fixture_rows())
    scoped_manifest = tmp_path / "scoped.json"
    with pytest.raises(fe.FinalEvaluationError, match="scope is inconsistent"):
        fe.run_evaluation(data, report_path, True, protocol(tmp_path, model_path), manifest_path=scoped_manifest,
                          sources_path=source_metadata(tmp_path), now=NOW)
    proto = protocol(tmp_path, model_path)
    write_json(proto, {**json.loads(proto.read_text(encoding="utf-8")), **with_scope})
    report = fe.run_evaluation(data, report_path, True, proto, manifest_path=scoped_manifest,
                               sources_path=source_metadata(tmp_path), now=NOW)
    assert report["evaluation_scope"] == with_scope["evaluation_scope"]
    assert report["overlap_check"]["out_of_scope_sources"][0]["name"] == "older_features"
    assert "older_features" in report["overlap_check"]["statement"]

    result = fe.preflight(protocol(tmp_path, model_path, approved=False), scoped_manifest, model_path=model_path)
    assert "scope: older_features is out of scope in the manifest but not excluded in protocol.json" in result["blockers"]


def test_per_domain_cap_and_class_maximum(tmp_path, model_path):
    rows = [[f"https://www.big.example.org/page/{name}", "legitimate", "official", "2026-10-02T00:00:00Z"]
            for name in ("alpha", "beta", "gamma", "delta", "epsilon")]
    rows += [[f"https://site{i}.org/home", "legitimate", "official", "2026-10-02T00:00:00Z"] for i in range(3)]
    rows += [[f"http://campaign.bad.test/{name}/login", "phishing", "feed", "2026-10-02T00:00:00Z"]
             for name in ("a", "b", "c", "d")]
    rows += [[f"http://p{i}.evil{i}.test/x", "phishing", "feed", "2026-10-02T00:00:00Z"] for i in range(4)]
    index = fe.load_historical_index(manifest(tmp_path))
    parsed, early, errors = fe.read_dataset(dataset(tmp_path, rows), fe.parse_utc(CUTOFF), NOW)
    cleaned, steps, _ = fe.clean_dataset(parsed, early, errors, index, max_per_domain=2, seed=42)
    cap = step(steps, "per_domain_cap")
    assert cap["max_per_registrable_domain"] == 2
    assert cap["removed"]["by_class"] == {"legitimate": 3, "phishing": 2}
    per_domain = {}
    for row in cleaned:
        per_domain[(row.label, row.keys.domain)] = per_domain.get((row.label, row.keys.domain), 0) + 1
    assert max(per_domain.values()) == 2
    again, _, _ = fe.clean_dataset(*fe.read_dataset(dataset(tmp_path, rows, "again.csv"), fe.parse_utc(CUTOFF), NOW),
                                   index, max_per_domain=2, seed=42)
    assert sorted(r.keys.normalized for r in again) == sorted(r.keys.normalized for r in cleaned)
    sample, size = fe.sample_balanced(cleaned, 42, 1, maximum=3)
    assert size == 3 and len(sample) == 6
    assert fe.sample_balanced(cleaned, 42, 1)[1] == 5

    output = tmp_path / "capped.json"
    proto = protocol(tmp_path, model_path)
    data = json.loads(proto.read_text(encoding="utf-8"))
    data["sampling"].update({"maximum_rows_per_class": 10, "max_per_registrable_domain": 20})
    write_json(proto, data)
    report = fe.run_evaluation(dataset(tmp_path, fixture_rows(), "cap.csv"), output, False, proto,
                               manifest_path=manifest(tmp_path), sources_path=source_metadata(tmp_path), now=NOW)
    assert report["class_balance"]["evaluated"] == {"legitimate": 10, "phishing": 10}
    assert report["protocol"]["maximum_rows_per_class"] == 10
    assert step(report["cleaning_steps"], "per_domain_cap")["removed"]["total"] == 0
