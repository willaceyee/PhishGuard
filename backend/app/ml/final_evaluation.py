"""Final untouched evaluation of the frozen PhishGuard URL model.

Run from ``backend``::

    python -m app.ml.final_evaluation preflight
    python -m app.ml.final_evaluation validate --dataset <csv>
    python -m app.ml.final_evaluation run --final --dataset <csv>

The procedure, accepted input format, cleaning rules, and gates are documented in
docs/final_model_evaluation_plan.md. URLs are treated strictly as text: nothing in
this module opens, resolves, or requests any URL.
"""

import argparse
import csv
import hashlib
import ipaddress
import json
import random
import re
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import numpy as np
from publicsuffixlist import PublicSuffixList

from app.ml.evaluate import classification_metrics, sha256
from app.ml.features import MODEL_FEATURE_NAMES, extract_url_features
from app.ml.prepare_demo_data import generate_demo_rows
from app.ml.retrain_raw import load_phishtank_splits, usable_url
from app.ml.service import load_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = PROJECT_ROOT / "ml_model" / "final_evaluation"
DEFAULT_PROTOCOL = FINAL_DIR / "protocol.json"
DEFAULT_MANIFEST = FINAL_DIR / "historical_sources.json"
DEFAULT_TEST_SOURCES = FINAL_DIR / "test_sources.json"
DEFAULT_REPORT = PROJECT_ROOT / "ml_model" / "artifacts" / "final_untouched_evaluation.json"

REQUIRED_COLUMNS = ("url", "label", "source", "observed_at")
LABELS = {"legitimate": 0, "phishing": 1}
DEFAULT_PORTS = {"http": 80, "https": 443}
TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
UUID_SEGMENT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
HEX_SEGMENT = re.compile(r"^[0-9a-f]{8,}$")
TOKEN_SEGMENT = re.compile(r"^[a-z0-9_\-.=~]{16,}$")
PHISHTANK_COLUMNS = {"url", "verified", "verification_time", "online"}
PHISHTANK_SOURCE = "phishtank_verified_online"
COMMON_CRAWL_SOURCE = "commoncrawl_cc_main_2026_43_official"
OFFICIAL_DOMAIN_COLUMNS = ("domain", "organization", "sector", "country", "evidence_url", "verified_on")


class FinalEvaluationError(Exception):
    """A gate failed. Final mode stops instead of producing a partial result."""


# ---------------------------------------------------------------------------
# URL text handling (no network access)
# ---------------------------------------------------------------------------

_PSL = None


def public_suffix_list():
    """Return the PSL bundled with the pinned publicsuffixlist package.

    PublicSuffixList() with no source reads the list shipped inside the package;
    it never downloads an update. Private-section suffixes (for example
    github.io) are included, so each tenant of a hosting platform is its own
    registrable domain.
    """
    global _PSL
    if _PSL is None:
        _PSL = PublicSuffixList(only_icann=False)
    return _PSL


def canonical_host(hostname):
    host = hostname.strip().lower().rstrip(".")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def is_ip_host(host):
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def registrable_domain(host):
    """Registrable domain (eTLD+1) using the Public Suffix List.

    IP literals and hosts that are themselves a public suffix are returned as-is.
    """
    if is_ip_host(host):
        return host
    return public_suffix_list().privatesuffix(host) or host


def _upper_escapes(value):
    return re.sub(r"%[0-9a-fA-F]{2}", lambda match: match.group(0).upper(), value)


@dataclass(frozen=True)
class UrlKeys:
    normalized: str
    host: str
    domain: str
    template: str


def normalize_url(url, require_scheme=True):
    """Return the identity form used for duplicate and overlap checks.

    Rules: trim; scheme and host lower-cased; host converted to IDNA ASCII and a
    trailing dot removed; default ports (80 for http, 443 for https) removed;
    fragment removed; empty path becomes "/"; trailing slashes removed from any
    longer path; percent-escapes upper-cased; userinfo and query kept unchanged.
    """
    if not isinstance(url, str):
        raise ValueError("URL must be text")
    text = url.strip()
    if not text:
        raise ValueError("URL is empty")
    if any(character.isspace() for character in text):
        raise ValueError("URL contains whitespace")
    if "://" not in text:
        if require_scheme:
            raise ValueError("URL must be a full URL starting with http:// or https://")
        text = f"http://{text}"
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS or not parts.hostname:
        raise ValueError("Only full http:// and https:// URLs with a host are accepted")
    try:
        port = parts.port
    except ValueError as error:
        raise ValueError("URL has an invalid port") from error
    host = canonical_host(parts.hostname)
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    if "@" in parts.netloc:
        netloc = f"{parts.netloc.rpartition('@')[0]}@{netloc}"
    path = _upper_escapes(parts.path) or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query = _upper_escapes(parts.query)
    return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else ""), host


def template_segment(segment):
    value = segment.lower()
    if not value:
        return value
    if value.isdigit():
        return "{n}"
    if UUID_SEGMENT.match(value):
        return "{uuid}"
    if HEX_SEGMENT.match(value) and any(character.isdigit() for character in value):
        return "{hex}"
    if (
        TOKEN_SEGMENT.match(value)
        and any(character.isdigit() for character in value)
        and any(character.isalpha() for character in value)
    ):
        return "{token}"
    return re.sub(r"\d{2,}", "{n}", value)


def url_template(normalized, host):
    """Near-duplicate key: host without a leading "www.", templated path, and the
    sorted set of query-parameter names (values ignored). Scheme and port are
    ignored. See template_segment for the per-segment rule."""
    parts = urlsplit(normalized)
    base_host = host[4:] if host.startswith("www.") else host
    path = "/".join(template_segment(segment) for segment in parts.path.split("/"))
    names = sorted({name.lower() for name, _ in parse_qsl(parts.query, keep_blank_values=True)})
    return f"{base_host}{path}?{'&'.join(names)}"


def url_keys(url, require_scheme=True):
    normalized, host = normalize_url(url, require_scheme=require_scheme)
    return UrlKeys(normalized, host, registrable_domain(host), url_template(normalized, host))


def parse_utc(value):
    text = (value or "").strip()
    if not TIMESTAMP_PATTERN.match(text):
        raise ValueError(
            "observed_at must be ISO 8601 with seconds and a UTC offset, e.g. 2026-10-01T12:00:00Z"
        )
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def utc_text(moment):
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Protocol, model, and environment gates
# ---------------------------------------------------------------------------


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_json(path, expected_format):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != expected_format:
        raise FinalEvaluationError(f"{path} is not a {expected_format} file")
    return data


def load_protocol(path=DEFAULT_PROTOCOL):
    protocol = load_json(path, "phishguard-final-evaluation-protocol/1")
    protocol["cutoff"] = parse_utc(protocol["cutoff_utc"])
    return protocol


def check_model(protocol, model_path=None):
    expected = protocol["model"]
    path = resolve_path(model_path or expected["path"])
    if not path.is_file():
        raise FinalEvaluationError(f"Model file not found: {path}")
    digest = sha256(path)
    if digest != expected["sha256"]:
        raise FinalEvaluationError(
            f"Model SHA-256 {digest} does not match the frozen value {expected['sha256']}"
        )
    bundle = load_bundle(str(path))
    feature_names = list(bundle["feature_names"])
    problems = []
    if feature_names != list(expected["feature_names"]):
        problems.append("bundle feature order differs from the protocol")
    if feature_names != list(MODEL_FEATURE_NAMES):
        problems.append("bundle feature order differs from MODEL_FEATURE_NAMES")
    if "uses_https" in feature_names:
        problems.append("bundle includes uses_https")
    if float(bundle.get("threshold", 0.5)) != float(expected["threshold"]):
        problems.append(f"bundle threshold {bundle.get('threshold')} differs from {expected['threshold']}")
    if problems:
        raise FinalEvaluationError("Model check failed: " + "; ".join(problems))
    return {
        "path": str(path),
        "sha256": digest,
        "threshold": float(expected["threshold"]),
        "feature_names": feature_names,
        "model_type": bundle.get("model_type"),
        "trained_at": bundle.get("trained_at"),
    }, bundle


def check_public_suffix_version(protocol):
    pinned = protocol["public_suffix_list"]["version"]
    installed = metadata.version("publicsuffixlist")
    if installed != pinned:
        raise FinalEvaluationError(
            f"publicsuffixlist {installed} is installed; the protocol pins {pinned}"
        )
    return installed


def git_state():
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        dirty = git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "tracked_changes": None}
    return {"commit": commit, "tracked_changes": dirty.splitlines()}


# ---------------------------------------------------------------------------
# Historical sources (overlap exclusion)
# ---------------------------------------------------------------------------


def _csv_urls(handle, column="url"):
    reader = csv.DictReader(handle)
    if column not in (reader.fieldnames or ()):
        raise FinalEvaluationError(f"Historical file has no '{column}' column")
    for row in reader:
        yield row.get(column) or ""


def _zip_csv_handle(archive):
    names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if len(names) != 1:
        raise FinalEvaluationError("Historical archive must contain exactly one CSV")
    raw = archive.open(names[0])
    return (line.decode("utf-8-sig", errors="replace") for line in raw)


def used_tranco_homepages(tranco_zip, excluded_urls, count):
    """Reproduce the first `count` homepage URLs app.ml.retrain_raw drew from Tranco."""
    urls = []
    seen = set()
    with zipfile.ZipFile(tranco_zip) as archive:
        for index, row in enumerate(csv.reader(_zip_csv_handle(archive))):
            if len(urls) >= count:
                break
            if len(row) < 2:
                continue
            domain = row[1].strip()
            hostname = domain if index % 2 == 0 else f"www.{domain}"
            url = usable_url(f"https://{hostname}/")
            if url and url not in excluded_urls and url not in seen:
                seen.add(url)
                urls.append(url)
    if len(urls) != count:
        raise FinalEvaluationError(f"Tranco archive yielded {len(urls)} homepages; expected {count}")
    return urls


@dataclass
class HistoricalSource:
    name: str
    status: str
    detail: str = ""
    sha256: str = None
    urls: set = field(default_factory=set)
    domains: set = field(default_factory=set)
    hosts: set = field(default_factory=set)
    templates: set = field(default_factory=set)
    unparseable: int = 0
    rows: int = 0

    def add(self, raw_url):
        self.rows += 1
        try:
            keys = url_keys(raw_url, require_scheme=False)
        except ValueError:
            self.unparseable += 1
            return
        self.urls.add(keys.normalized)
        self.domains.add(keys.domain)
        self.hosts.add(keys.host)
        self.templates.add(keys.template)

    @property
    def checked(self):
        return self.status == "verified"

    def summary(self):
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "sha256": self.sha256,
            "rows": self.rows,
            "normalized_urls": len(self.urls),
            "registrable_domains": len(self.domains),
            "unparseable_rows": self.unparseable,
        }


def _load_exclusion_list(entry, source):
    spec = entry["exclusion_list"]
    path = resolve_path(spec["path"])
    if not path.is_file():
        return False
    digest = sha256(path)
    if digest != spec["sha256"]:
        raise FinalEvaluationError(f"Exclusion list for {source.name} has SHA-256 {digest}, expected {spec['sha256']}")
    data = load_json(path, "phishguard-exclusion-list/1")
    derived = data["derived_from"]
    if derived["sha256"] != entry["sha256"] or derived["name"] != entry["name"]:
        raise FinalEvaluationError(f"Exclusion list for {source.name} was not derived from the recorded source file")
    source.urls, source.domains = set(data["normalized_urls"]), set(data["registrable_domains"])
    source.hosts, source.templates = set(data["hosts"]), set(data["templates"])
    source.rows, source.unparseable = derived["rows"], derived["unparseable_rows"]
    source.status, source.detail = "verified", f"exclusion list {path.name} (SHA-256 verified)"
    return True


def load_historical_source(entry, by_name):
    source = HistoricalSource(entry["name"], "unchecked", sha256=entry.get("sha256"))
    kind = entry["format"]
    if kind == "out_of_scope":
        source.status, source.detail = "out_of_scope", entry.get("decision") or ""
        if not source.detail.strip():
            source.status, source.detail = "gap", "out_of_scope requires a recorded decision"
        return source
    if kind == "no_urls":
        source.status = "gap"
        source.detail = entry.get("note") or "Source has no URL column; overlap cannot be checked."
        return source
    if kind == "synthetic_demo_generator":
        rows = generate_demo_rows(entry["samples_per_class"], entry["seed"])
        for row in rows:
            source.add(row["url"])
        source.sha256 = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        source.status, source.detail = "verified", "regenerated deterministically"
        return source

    path = resolve_path(entry["path"])
    if not path.is_file():
        if entry.get("exclusion_list") and _load_exclusion_list(entry, source):
            return source
        source.status, source.detail = "missing", f"file not found: {entry['path']}"
        return source
    digest = sha256(path)
    if digest != entry["sha256"]:
        source.status, source.detail = "checksum_mismatch", f"SHA-256 {digest} != recorded {entry['sha256']}"
        return source

    if kind == "phishtank_csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for url in _csv_urls(handle):
                source.add(url)
    elif kind == "url_csv_zip":
        with zipfile.ZipFile(path) as archive:
            for url in _csv_urls(_zip_csv_handle(archive)):
                source.add(url)
    elif kind == "tranco_used_homepages":
        phishing_entry = by_name[entry["phishing_source"]]
        phishing_path = resolve_path(phishing_entry["path"])
        if not phishing_path.is_file() or sha256(phishing_path) != phishing_entry["sha256"]:
            source.status = "missing"
            source.detail = f"needs the verified {phishing_entry['name']} file to reproduce which entries were used"
            return source
        splits, _ = load_phishtank_splits(
            phishing_path, parse_utc(entry["train_end"]), parse_utc(entry["diagnostic_start"])
        )
        phishing_counts = {name: len(urls) for name, urls in splits.items()}
        if phishing_counts != entry["expected_phishing_rows"]:
            raise FinalEvaluationError(
                f"PhishTank split sizes {phishing_counts} do not match the recorded training run "
                f"{entry['expected_phishing_rows']}"
            )
        needed = {name: count - count // 2 for name, count in phishing_counts.items()}
        if needed != entry["expected_homepages"]:
            raise FinalEvaluationError(f"Tranco counts {needed} differ from {entry['expected_homepages']}")
        excluded = set().union(*map(set, splits.values()))
        for url in used_tranco_homepages(path, excluded, sum(needed.values())):
            source.add(url)
    else:
        raise FinalEvaluationError(f"Unknown historical source format: {kind}")
    source.status, source.detail = "verified", f"{path.name} (SHA-256 verified)"
    return source


@dataclass
class HistoricalIndex:
    sources: list

    def __post_init__(self):
        self.url_sources = defaultdict(set)
        self.domain_sources = defaultdict(set)
        self.hosts = set()
        self.templates = set()
        for source in self.sources:
            for url in source.urls:
                self.url_sources[url].add(source.name)
            for domain in source.domains:
                self.domain_sources[domain].add(source.name)
            self.hosts |= source.hosts
            self.templates |= source.templates

    @property
    def gaps(self):
        return [source for source in self.sources if source.status not in ("verified", "out_of_scope")]

    @property
    def out_of_scope(self):
        return [source for source in self.sources if source.status == "out_of_scope"]


def load_historical_index(manifest_path=DEFAULT_MANIFEST):
    manifest = load_json(manifest_path, "phishguard-historical-sources/1")
    by_name = {entry["name"]: entry for entry in manifest["sources"]}
    return HistoricalIndex([load_historical_source(entry, by_name) for entry in manifest["sources"]])


def build_exclusion_list(manifest_path, source_name, output_path):
    manifest = load_json(manifest_path, "phishguard-historical-sources/1")
    by_name = {entry["name"]: entry for entry in manifest["sources"]}
    entry = by_name[source_name]
    source = load_historical_source({**entry, "exclusion_list": None}, by_name)
    if source.status != "verified":
        raise FinalEvaluationError(f"Cannot build an exclusion list for {source_name}: {source.status} ({source.detail})")
    data = {
        "format": "phishguard-exclusion-list/1",
        "derived_from": {
            "name": entry["name"], "format": entry["format"], "sha256": entry["sha256"],
            "rows": source.rows, "unparseable_rows": source.unparseable,
        },
        "rules": "normalize_url / registrable_domain / url_template in app.ml.final_evaluation",
        "public_suffix_list_version": metadata.version("publicsuffixlist"),
        "code_commit": git_state()["commit"],
        "normalized_urls": sorted(source.urls),
        "registrable_domains": sorted(source.domains),
        "hosts": sorted(source.hosts),
        "templates": sorted(source.templates),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return {"output": str(output_path), "sha256": sha256(output_path), "rows": source.rows}


# ---------------------------------------------------------------------------
# Test-set input
# ---------------------------------------------------------------------------


@dataclass
class HoldoutRow:
    line: int
    url: str
    label: str
    source: str
    observed_at: datetime
    keys: UrlKeys
    represents: set = field(default_factory=set)

    @property
    def target(self):
        return LABELS[self.label]


def read_dataset(path, cutoff, now=None):
    """Parse and validate a final-test CSV.

    Returns (rows_after_cutoff, rows_at_or_before_cutoff, errors). Errors are
    (line, reason) pairs; URLs are never echoed.
    """
    now = now or datetime.now(timezone.utc)
    rows, early, errors = [], [], []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or ())]
        if missing:
            raise FinalEvaluationError(f"Dataset is missing required columns: {', '.join(missing)}")
        for line, record in enumerate(reader, start=2):
            label = (record.get("label") or "").strip()
            source = (record.get("source") or "").strip()
            if label not in LABELS:
                errors.append((line, "label must be exactly 'phishing' or 'legitimate'"))
                continue
            if not source:
                errors.append((line, "source is empty"))
                continue
            try:
                observed_at = parse_utc(record.get("observed_at"))
            except ValueError as error:
                errors.append((line, str(error)))
                continue
            if observed_at > now:
                errors.append((line, "observed_at is in the future"))
                continue
            try:
                keys = url_keys(record.get("url"), require_scheme=True)
                extract_url_features(record["url"].strip())
            except ValueError as error:
                errors.append((line, f"invalid URL: {error}"))
                continue
            row = HoldoutRow(line, record["url"].strip(), label, source, observed_at, keys, {keys.normalized})
            (rows if observed_at > cutoff else early).append(row)
    return rows, early, errors


def read_datasets(paths, cutoff, now=None):
    """Read one or more final-test CSVs; rows are identified as (file number, line)."""
    rows, early, errors = [], [], []
    for number, path in enumerate(paths):
        file_rows, file_early, file_errors = read_dataset(path, cutoff, now)
        for row in file_rows + file_early:
            row.line = (number, row.line)
        rows += file_rows
        early += file_early
        errors += [(f"{Path(path).name}:{line}", reason) for line, reason in file_errors]
    return rows, early, errors


def tally(rows):
    by_class = Counter(row.label for row in rows)
    by_source = defaultdict(Counter)
    for row in rows:
        by_source[row.source][row.label] += 1
    return {
        "total": len(rows),
        "by_class": {label: by_class.get(label, 0) for label in LABELS},
        "by_source": {source: dict(counts) for source, counts in sorted(by_source.items())},
    }


def _earliest(rows):
    return min(rows, key=lambda row: (row.observed_at, row.keys.normalized, row.line))


def _collapse(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[(row.label, key(row))].append(row)
    kept, removed = [], []
    for members in groups.values():
        keeper = _earliest(members)
        for member in members:
            if member is not keeper:
                keeper.represents |= member.represents
                removed.append(member)
        kept.append(keeper)
    kept.sort(key=lambda row: row.line)
    return kept, removed


def clean_dataset(rows, early, errors, index):
    """Apply the documented cleaning steps in order and count every removal."""
    steps = [
        {"step": "input_rows_after_validation", "remaining": tally(rows + early)},
        {"step": "rejected_malformed_rows", "removed_rows": len(errors)},
        {"step": "removed_at_or_before_cutoff", "removed": tally(early), "remaining": tally(rows)},
    ]
    exact_kept, exact_removed = _collapse(rows, lambda row: row.keys.normalized)
    steps.append({"step": "exact_duplicates_after_normalization", "removed": tally(exact_removed), "remaining": tally(exact_kept)})
    labels_by_url = defaultdict(set)
    for row in exact_kept:
        labels_by_url[row.keys.normalized].add(row.label)
    conflicting = {url for url, labels in labels_by_url.items() if len(labels) > 1}

    near_kept, near_removed = _collapse(exact_kept, lambda row: row.keys.template)
    steps.append({"step": "near_duplicates_by_template", "removed": tally(near_removed), "remaining": tally(near_kept)})

    leakage_before = template_leakage(near_kept, index)
    url_hits = [row for row in near_kept if any(url in index.url_sources for url in row.represents)]
    hit_ids = {id(row) for row in url_hits}
    after_url = [row for row in near_kept if id(row) not in hit_ids]
    steps.append({
        "step": "historical_normalized_url_overlap",
        "removed": tally(url_hits),
        "matched_sources": dict(Counter(
            name for row in url_hits for url in row.represents for name in index.url_sources.get(url, ())
        )),
        "remaining": tally(after_url),
    })
    domain_hits = [row for row in after_url if row.keys.domain in index.domain_sources]
    after_domain = [row for row in after_url if row.keys.domain not in index.domain_sources]
    steps.append({
        "step": "historical_registrable_domain_overlap",
        "removed": tally(domain_hits),
        "matched_sources": dict(Counter(
            name for row in domain_hits for name in index.domain_sources[row.keys.domain]
        )),
        "remaining": tally(after_domain),
    })
    conflict_hits = [row for row in after_domain if row.represents & conflicting]
    cleaned = [row for row in after_domain if not row.represents & conflicting]
    steps.append({
        "step": "conflicting_labels",
        "conflicting_normalized_urls": len(conflicting),
        "removed": tally(conflict_hits),
        "remaining": tally(cleaned),
    })
    leakage = {"before_overlap_removal": leakage_before, "after_cleaning": template_leakage(cleaned, index)}
    return cleaned, steps, leakage


def template_leakage(rows, index):
    return {
        "rows": len(rows),
        "sharing_host_with_history": sum(row.keys.host in index.hosts for row in rows),
        "sharing_path_template_with_history": sum(row.keys.template in index.templates for row in rows),
    }


def sample_balanced(rows, seed, minimum):
    by_class = {label: sorted((row for row in rows if row.label == label), key=lambda row: row.keys.normalized) for label in LABELS}
    for label, members in by_class.items():
        if not members:
            raise FinalEvaluationError(f"No {label} rows remain after cleaning; the evaluation cannot run.")
        if len(members) < minimum:
            raise FinalEvaluationError(
                f"Only {len(members)} {label} rows remain after cleaning; the protocol requires {minimum}."
            )
    size = min(len(members) for members in by_class.values())
    rng = random.Random(seed)
    sample = rng.sample(by_class["legitimate"], size) + rng.sample(by_class["phishing"], size)
    return sample, size


# ---------------------------------------------------------------------------
# Test-source provenance
# ---------------------------------------------------------------------------

REQUIRED_SOURCE_FIELDS = (
    "label", "publisher", "access_url", "documentation_url", "snapshot_downloaded_at_utc",
    "terms", "label_definition", "timestamp_field", "sampling_rule", "coverage_notes",
)


def check_test_sources(path, used_sources, strict):
    data = load_json(path, "phishguard-final-test-sources/1")
    declared = data["sources"]
    problems, raw_files = [], {}
    for name in sorted(used_sources):
        if name not in declared:
            problems.append(f"source '{name}' is not declared in {Path(path).name}")
            continue
        entry = declared[name]
        for key in REQUIRED_SOURCE_FIELDS:
            if entry.get(key) in (None, "", []):
                problems.append(f"{name}: '{key}' is not recorded")
        for raw in entry.get("raw_files") or []:
            raw_path = resolve_path(raw["path"])
            if not raw_path.is_file():
                problems.append(f"{name}: raw file not found: {raw['path']}")
            elif sha256(raw_path) != raw.get("sha256"):
                problems.append(f"{name}: raw file checksum differs for {raw['path']}")
            else:
                raw_files[raw["path"]] = raw["sha256"]
        if not entry.get("raw_files"):
            problems.append(f"{name}: no raw_files with checksums recorded")
    if strict and problems:
        raise FinalEvaluationError("Test-source metadata incomplete:\n  - " + "\n  - ".join(problems))
    return {"declared": {name: declared[name] for name in used_sources if name in declared}, "problems": problems, "raw_files": raw_files}


def check_source_labels(rows, declared):
    mismatched = Counter(
        row.source for row in rows if row.source in declared and declared[row.source].get("label") != row.label
    )
    if mismatched:
        raise FinalEvaluationError(f"Rows disagree with their source's declared label: {dict(mismatched)}")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def breakdown(rows, probabilities, threshold):
    def summarize(members):
        correct = sum(int(probabilities[i] >= threshold) == row.target for i, row in members)
        return {"rows": len(members), "correct": correct, "accuracy": round(correct / len(members), 6)}

    indexed = list(enumerate(rows))
    by_source, by_week = defaultdict(list), defaultdict(list)
    for item in indexed:
        row = item[1]
        by_source[(row.source, row.label)].append(item)
        year, week, _ = row.observed_at.isocalendar()
        by_week[(f"{year}-W{week:02d}", row.label)].append(item)
    return {
        "by_source": {f"{source} ({label})": summarize(members) for (source, label), members in sorted(by_source.items())},
        "by_observation_week": {f"{week} ({label})": summarize(members) for (week, label), members in sorted(by_week.items())},
        "note": "For a phishing group accuracy is recall; for a legitimate group it is specificity.",
    }


def run_evaluation(
    dataset, output, final, protocol_path=DEFAULT_PROTOCOL, manifest_path=DEFAULT_MANIFEST,
    sources_path=DEFAULT_TEST_SOURCES, model_path=None, now=None,
):
    protocol = load_protocol(protocol_path)
    output = Path(output)
    git = git_state()
    if final:
        gates = []
        if not protocol.get("approved"):
            gates.append("protocol.json is not approved")
        if output.resolve() != DEFAULT_REPORT.resolve():
            gates.append(f"final reports are written only to {DEFAULT_REPORT}")
        if output.exists():
            gates.append(f"{output} already exists; the final evaluation runs once")
        if git["commit"] is None:
            gates.append("Git commit could not be determined")
        elif git["tracked_changes"]:
            gates.append("tracked files have uncommitted changes")
        if gates:
            raise FinalEvaluationError("Final run refused:\n  - " + "\n  - ".join(gates))
    elif output.resolve() == DEFAULT_REPORT.resolve():
        raise FinalEvaluationError("Development runs must write to a different --output path")

    model_info, bundle = check_model(protocol, model_path)
    psl_version = check_public_suffix_version(protocol)
    index = load_historical_index(manifest_path)
    if final and index.gaps:
        raise FinalEvaluationError(
            "Historical overlap cannot be fully checked:\n  - "
            + "\n  - ".join(f"{source.name}: {source.status} ({source.detail})" for source in index.gaps)
        )

    datasets = [dataset] if isinstance(dataset, (str, Path)) else list(dataset)
    rows, early, errors = read_datasets(datasets, protocol["cutoff"], now)
    if final and errors:
        raise FinalEvaluationError(f"{len(errors)} malformed rows; run 'validate' and correct the input file")
    sources = check_test_sources(sources_path, {row.source for row in rows + early}, strict=final)
    check_source_labels(rows + early, sources["declared"])

    cleaned, steps, leakage = clean_dataset(rows, early, errors, index)
    sampling = protocol["sampling"]
    sample, per_class = sample_balanced(cleaned, sampling["seed"], sampling["minimum_rows_per_class"])
    steps.append({
        "step": "balanced_sampling",
        "method": sampling["method"],
        "seed": sampling["seed"],
        "removed": {"total": len(cleaned) - len(sample)},
        "remaining": tally(sample),
    })

    feature_names = model_info["feature_names"]
    matrix = np.asarray(
        [[extract_url_features(row.url)[name] for name in feature_names] for row in sample], dtype=float
    )
    probabilities = bundle["model"].predict_proba(matrix)[:, 1]
    labels = [row.target for row in sample]
    threshold = model_info["threshold"]
    metrics = classification_metrics(labels, probabilities, threshold)

    cleaned_balance = tally(cleaned)["by_class"]
    checked = [source.name for source in index.sources if source.checked]
    report = {
        "report_type": "final untouched evaluation" if final else "DEVELOPMENT FIXTURE RUN - NOT A FINAL RESULT",
        "final": bool(final),
        "generated_at": utc_text(datetime.now(timezone.utc)),
        "model": model_info,
        "evaluation_code": {"commit": git["commit"], "uncommitted_tracked_changes": git["tracked_changes"]},
        "protocol": {
            "sha256": sha256(protocol_path),
            "approved": bool(protocol.get("approved")),
            "cutoff_utc": utc_text(protocol["cutoff"]),
            "random_seed": sampling["seed"],
            "sampling_method": sampling["method"],
            "minimum_rows_per_class": sampling["minimum_rows_per_class"],
            "threshold": threshold,
            "public_suffix_list": {"package": "publicsuffixlist", "version": psl_version, "private_suffixes": True},
        },
        "feature_names": feature_names,
        "inputs": {
            "datasets": [{"path": str(path), "sha256": sha256(path)} for path in datasets],
            "historical_manifest_sha256": sha256(manifest_path),
            "test_sources_sha256": sha256(sources_path),
            "raw_source_files": sources["raw_files"],
        },
        "test_sources": sources["declared"],
        "test_source_problems": sources["problems"],
        "historical_sources": [source.summary() for source in index.sources],
        "overlap_check": {
            "checked_sources": checked,
            "out_of_scope_sources": [{"name": s.name, "decision": s.detail} for s in index.out_of_scope],
            "unchecked_sources": [{"name": s.name, "status": s.status, "detail": s.detail} for s in index.gaps],
            "statement": (
                "Disjoint (normalized URL and registrable domain) from every checked historical source listed."
                if not index.gaps else
                "NOT fully checked: overlap with the unchecked sources listed is unknown."
            ),
        },
        "cleaning_steps": steps,
        "template_leakage": leakage,
        "class_balance": {
            "after_cleaning": cleaned_balance,
            "after_cleaning_phishing_share": round(cleaned_balance["phishing"] / max(len(cleaned), 1), 6),
            "evaluated": {"legitimate": per_class, "phishing": per_class},
            "evaluated_phishing_share": 0.5,
            "note": (
                "Accuracy and PR-AUC depend on the class composition of the test set; PR-AUC for a "
                "random ranking equals the phishing share (0.5 here). Precision for each class also "
                "depends on prevalence, so results do not transfer directly to a different mix."
            ),
        },
        "metrics": metrics,
        "breakdown": breakdown(sample, probabilities, threshold),
        "limitations": [
            "Lexical-only model: no page content, hosting, or reputation data.",
            "Concept drift: the result applies to the collection window only.",
            "Source coverage: one phishing feed (online, verified entries only) and one benign source built from an official-domain allowlist.",
            "Label noise in external sources is possible.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if final else "w"
    with output.open(mode, encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2))
    return report


# ---------------------------------------------------------------------------
# Source converters (operate on downloaded files only)
# ---------------------------------------------------------------------------


def _write_rows(path, rows, extra=()):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*REQUIRED_COLUMNS, *extra])
        writer.writeheader()
        writer.writerows(rows)


def convert_phishtank(input_csv, output_csv):
    """Convert PhishTank's online-valid CSV to the final-test format.

    observed_at is PhishTank's per-row verification_time. Rows not marked
    verified=yes and online=yes are dropped and counted.
    """
    rows, skipped = [], Counter()
    with Path(input_csv).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not PHISHTANK_COLUMNS.issubset(reader.fieldnames or ()):
            raise FinalEvaluationError("PhishTank CSV must contain url, verified, verification_time, and online")
        for record in reader:
            if (record.get("verified") or "").lower() != "yes" or (record.get("online") or "").lower() != "yes":
                skipped["not_verified_online"] += 1
                continue
            try:
                observed_at = utc_text(parse_utc(record["verification_time"]))
            except ValueError:
                skipped["invalid_verification_time"] += 1
                continue
            rows.append({
                "url": (record.get("url") or "").strip(), "label": "phishing", "source": PHISHTANK_SOURCE,
                "observed_at": observed_at, "phish_id": record.get("phish_id", ""),
            })
    _write_rows(output_csv, rows, extra=("phish_id",))
    return {"input_sha256": sha256(input_csv), "output_sha256": sha256(output_csv), "rows": len(rows), "skipped": dict(skipped)}


def read_official_domains(path):
    domains = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OFFICIAL_DOMAIN_COLUMNS:
            raise FinalEvaluationError(f"Official-domain list must have columns: {','.join(OFFICIAL_DOMAIN_COLUMNS)}")
        for line, record in enumerate(reader, start=2):
            domain = canonical_host(record["domain"])
            if registrable_domain(domain) != domain or is_ip_host(domain):
                raise FinalEvaluationError(f"Line {line}: '{record['domain']}' is not a registrable domain")
            if any(not (record.get(column) or "").strip() for column in OFFICIAL_DOMAIN_COLUMNS):
                raise FinalEvaluationError(f"Line {line}: every column must be filled in")
            domains[domain] = record
    return domains


def convert_common_crawl(index_files, official_domains_csv, output_csv, max_per_domain, seed,
                         phishing_csv=None, source_name=COMMON_CRAWL_SOURCE):
    """Build legitimate rows from Common Crawl URL-index records (JSON lines).

    Benign-label rule: a capture is kept only if its host is an allow-listed
    official registrable domain or a subdomain of one, the capture returned HTTP
    200 with an HTML MIME type, the URL has no userinfo, IP host, or non-default
    port, and the domain does not occur in the supplied phishing feed. A crawl
    timestamp or a 200 response alone never establishes a benign label.
    """
    allowed = read_official_domains(official_domains_csv)
    contested = set()
    if phishing_csv:
        with Path(phishing_csv).open(newline="", encoding="utf-8-sig") as handle:
            for url in _csv_urls(handle):
                try:
                    contested.add(url_keys(url, require_scheme=False).domain)
                except ValueError:
                    continue
    skipped = Counter()
    candidates = {}
    for index_file in index_files:
        with Path(index_file).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    keys = url_keys(record["url"])
                    parts = urlsplit(record["url"].strip())
                    observed = datetime.strptime(record["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                except (ValueError, KeyError, TypeError):
                    skipped["unparseable_record"] += 1
                    continue
                mime = (record.get("mime-detected") or record.get("mime") or "").lower()
                if str(record.get("status")) != "200" or not mime.startswith("text/html"):
                    skipped["not_200_html"] += 1
                elif "@" in parts.netloc or is_ip_host(keys.host) or parts.port not in (None, DEFAULT_PORTS[parts.scheme.lower()]):
                    skipped["userinfo_ip_or_port"] += 1
                elif keys.domain not in allowed:
                    skipped["domain_not_allow_listed"] += 1
                elif keys.domain in contested:
                    skipped["domain_in_phishing_feed"] += 1
                else:
                    existing = candidates.get(keys.normalized)
                    if existing is None or observed < existing[1]:
                        candidates[keys.normalized] = (record["url"].strip(), observed, keys.domain)
    per_domain = defaultdict(list)
    for normalized, (url, observed, domain) in candidates.items():
        per_domain[domain].append((hashlib.sha256(f"{seed}:{normalized}".encode()).hexdigest(), url, observed, domain))
    rows = []
    for domain in sorted(per_domain):
        for _, url, observed, _ in sorted(per_domain[domain])[:max_per_domain]:
            rows.append({
                "url": url, "label": "legitimate", "source": source_name, "observed_at": utc_text(observed),
                "domain": domain, "sector": allowed[domain]["sector"],
            })
    _write_rows(output_csv, rows, extra=("domain", "sector"))
    return {
        "official_domains_sha256": sha256(official_domains_csv),
        "index_files_sha256": {str(path): sha256(path) for path in index_files},
        "phishing_feed_sha256": sha256(phishing_csv) if phishing_csv else None,
        "output_sha256": sha256(output_csv),
        "rows": len(rows),
        "domains_with_rows": len(per_domain),
        "contested_domains_excluded": sorted(contested & set(allowed)),
        "max_per_domain": max_per_domain,
        "seed": seed,
        "skipped": dict(skipped),
    }


# ---------------------------------------------------------------------------
# Preflight and CLI
# ---------------------------------------------------------------------------


def preflight(protocol_path=DEFAULT_PROTOCOL, manifest_path=DEFAULT_MANIFEST, official_domains=None, model_path=None):
    protocol = load_protocol(protocol_path)
    result = {"protocol_approved": bool(protocol.get("approved")), "cutoff_utc": utc_text(protocol["cutoff"]), "blockers": []}
    try:
        result["model"], _ = check_model(protocol, model_path)
    except FinalEvaluationError as error:
        result["blockers"].append(str(error))
    try:
        result["public_suffix_list_version"] = check_public_suffix_version(protocol)
    except FinalEvaluationError as error:
        result["blockers"].append(str(error))
    index = load_historical_index(manifest_path)
    result["historical_sources"] = [source.summary() for source in index.sources]
    result["blockers"] += [f"historical source {s.name}: {s.status} ({s.detail})" for s in index.gaps]
    if official_domains:
        allowed = read_official_domains(official_domains)
        result["official_domains"] = len(allowed)
        result["official_domains_seen_in_history"] = sorted(set(allowed) & set(index.domain_sources))
    git = git_state()
    result["git"] = git
    if not result["protocol_approved"]:
        result["blockers"].append("protocol.json is not approved")
    if git["tracked_changes"]:
        result["blockers"].append("tracked files have uncommitted changes")
    result["ready_for_final_run"] = not result["blockers"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Final untouched evaluation of the frozen PhishGuard model.")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--historical-manifest", type=Path, default=DEFAULT_MANIFEST)
    commands = parser.add_subparsers(dest="command", required=True)

    pre = commands.add_parser("preflight", help="Check model, protocol, and historical sources (no test data).")
    pre.add_argument("--official-domains", type=Path)
    pre.add_argument("--model", type=Path)

    excl = commands.add_parser("build-exclusions", help="Derive a verifiable exclusion list from one historical source.")
    excl.add_argument("--source", required=True)
    excl.add_argument("--output", type=Path, required=True)

    val = commands.add_parser("validate", help="Validate a final-test CSV (format and provenance only).")
    val.add_argument("--dataset", type=Path, nargs="+", required=True)
    val.add_argument("--test-sources", type=Path, default=DEFAULT_TEST_SOURCES)

    run = commands.add_parser("run", help="Run the evaluation.")
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--final", action="store_true", help="The single final run (all gates enforced).")
    mode.add_argument("--development-fixture", action="store_true", help="Exercise the pipeline on non-test data.")
    run.add_argument("--dataset", type=Path, nargs="+", required=True)
    run.add_argument("--test-sources", type=Path, default=DEFAULT_TEST_SOURCES)
    run.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    run.add_argument("--model", type=Path)

    pt = commands.add_parser("convert-phishtank", help="Convert a downloaded PhishTank online-valid CSV.")
    pt.add_argument("--input", type=Path, required=True)
    pt.add_argument("--output", type=Path, required=True)

    cc = commands.add_parser("convert-common-crawl", help="Build legitimate rows from Common Crawl index JSON lines.")
    cc.add_argument("--index", type=Path, nargs="+", required=True)
    cc.add_argument("--official-domains", type=Path, required=True)
    cc.add_argument("--output", type=Path, required=True)
    cc.add_argument("--max-per-domain", type=int, required=True)
    cc.add_argument("--seed", type=int, required=True)
    cc.add_argument("--phishing-feed", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight(args.protocol, args.historical_manifest, args.official_domains, args.model)
            print(json.dumps(result, indent=2))
            return 0 if result["ready_for_final_run"] else 1
        if args.command == "build-exclusions":
            print(json.dumps(build_exclusion_list(args.historical_manifest, args.source, args.output), indent=2))
            return 0
        if args.command == "validate":
            protocol = load_protocol(args.protocol)
            rows, early, errors = read_datasets(args.dataset, protocol["cutoff"])
            sources = check_test_sources(args.test_sources, {row.source for row in rows + early}, strict=False)
            check_source_labels(rows + early, sources["declared"])
            reasons = Counter(reason for _, reason in errors)
            print(json.dumps({
                "datasets_sha256": {str(path): sha256(path) for path in args.dataset},
                "valid_rows_after_cutoff": tally(rows),
                "rows_at_or_before_cutoff": len(early),
                "malformed_rows": len(errors),
                "malformed_reasons": dict(reasons),
                "malformed_lines_first_20": [line for line, _ in errors[:20]],
                "test_source_problems": sources["problems"],
            }, indent=2))
            return 0 if not errors and not sources["problems"] else 1
        if args.command == "run":
            report = run_evaluation(
                args.dataset, args.output, args.final, args.protocol, args.historical_manifest,
                args.test_sources, args.model,
            )
            print(json.dumps({"report": str(args.output), "metrics": report["metrics"]}, indent=2))
            return 0
        if args.command == "convert-phishtank":
            print(json.dumps(convert_phishtank(args.input, args.output), indent=2))
            return 0
        print(json.dumps(convert_common_crawl(
            args.index, args.official_domains, args.output, args.max_per_domain, args.seed, args.phishing_feed,
        ), indent=2))
        return 0
    except FinalEvaluationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
