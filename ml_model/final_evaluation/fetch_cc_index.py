"""Download Common Crawl URL-index records for the official-domain list.

Run from ``backend`` only after collection is authorized:

    python ..\\ml_model\\final_evaluation\\fetch_cc_index.py            # download
    python ..\\ml_model\\final_evaluation\\fetch_cc_index.py --dry-run  # list requests only

For each domain in official_domains.csv this asks Common Crawl's public index server
for every capture of that domain and its subdomains in CC-MAIN-2026-43 that returned
HTTP 200 with an HTML type. It reads index records only (URL, capture time, status,
MIME type); it never contacts the listed websites. Each domain is saved as one JSON
Lines file in ml_model/data/final/raw/cc-index/, and download_record.json records,
per domain, the request time, the filters used, the outcome ("captured" or
"no_matching_captures") and the file's SHA-256. Failed requests are listed under
"failures" and write no file. On resume a domain is skipped only when its entry was
made with the current filters and its file still matches the recorded checksum; the
script exits non-zero while any domain has failed, so a wrapper can retry.
"""

import argparse
import csv
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = ROOT / "ml_model" / "final_evaluation" / "official_domains.csv"
OUTPUT = ROOT / "ml_model" / "data" / "final" / "raw" / "cc-index"
INDEX = "https://index.commoncrawl.org/CC-MAIN-2026-43-index"
FIELDS = "url,timestamp,status,mime,mime-detected,digest"
USER_AGENT = "PhishGuard-capstone-evaluation/1.0 (academic research; index lookup only)"
DELAY_SECONDS = 2.0
# Exact match on the detected type. The index server returned no rows for the
# "~mime-detected:html" form (checked 2026-11-26), so "~" does not mean "contains"
# here. The converter keeps only types starting with text/html, so this applies
# the same rule earlier.
MIME_FILTERS = ["=mime-detected:text/html"]
FILTERS = ["status:200", *MIME_FILTERS]

try:
    # Use certifi's current CA bundle when installed: some Windows certificate stores
    # hold an expired root that makes verification fail. Verification stays on.
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def query(domain, **extra):
    params = [("url", domain), ("matchType", "domain"), ("output", "json"), ("fl", FIELDS),
              *[("filter", f) for f in FILTERS], *extra.items()]
    return f"{INDEX}?{urllib.parse.urlencode(params)}"


def fetch(url, attempts=5):
    """Return the response text, or None when the server answers 404 ("No Captures found")."""
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
        time.sleep(DELAY_SECONDS * 2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def is_complete(entry, target):
    """A domain is skipped on resume only if it was fetched with the current filters and its
    file is unchanged. Entries without a filter stamp (older runs) are fetched again."""
    return (
        entry is not None
        and entry.get("filters") == FILTERS
        and entry.get("outcome") in ("captured", "no_matching_captures")
        and target.is_file()
        and hashlib.sha256(target.read_bytes()).hexdigest() == entry.get("sha256")
    )


def download_domain(domain, target, fetcher=fetch, delay=DELAY_SECONDS):
    """Fetch every index page for one domain. Raises on a failed request, so nothing is
    written and the domain is retried later. Returns the per-domain record entry."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pages_text = fetcher(query(domain, showNumPages="true"))
    pages = json.loads(pages_text).get("pages", 0) if pages_text and pages_text.strip() else 0
    lines, pages_not_found, off_filter = [], 0, 0
    for page in range(pages):
        time.sleep(delay)
        text = fetcher(query(domain, page=str(page)))
        if text is None:
            pages_not_found += 1
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("status")) != "200" or row.get("mime-detected") != "text/html":
                off_filter += 1  # defensive check that the server applied the filters
            lines.append(line)
    if off_filter:
        raise RuntimeError(f"{domain}: {off_filter} returned rows do not match {FILTERS}")
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {
        "requested_at_utc": started,
        "filters": list(FILTERS),
        "outcome": "captured" if lines else "no_matching_captures",
        "pages": pages,
        "pages_not_found": pages_not_found,
        "records": len(lines),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def collect(domains, output, fetcher=fetch, delay=DELAY_SECONDS, log=print):
    """Download every domain not yet complete. Returns the record; failures are listed in
    record["failures"] and retried on the next call."""
    output.mkdir(parents=True, exist_ok=True)
    record_path = output / "download_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else None
    if record is not None and record.get("filters") != FILTERS:
        raise SystemExit(f"{record_path} was made with filters {record.get('filters')}, not {FILTERS}; "
                         "move that folder aside before downloading again.")
    record = record or {
        "index": INDEX, "fields": FIELDS, "filters": list(FILTERS),
        "official_domains_sha256": hashlib.sha256(DOMAINS.read_bytes()).hexdigest(),
        "domains": {}, "failures": {},
    }
    record.setdefault("failures", {})
    for number, domain in enumerate(domains, start=1):
        target = output / f"{domain}.jsonl"
        if is_complete(record["domains"].get(domain), target):
            continue
        record["domains"].pop(domain, None)
        try:
            entry = download_domain(domain, target, fetcher, delay)
        except Exception as error:  # noqa: BLE001 - every failure is logged and retried
            record["failures"][domain] = {
                "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "error": f"{type(error).__name__}: {error}"[:300],
            }
            log(f"[{number}/{len(domains)}] {domain}: FAILED ({record['failures'][domain]['error']})")
        else:
            record["domains"][domain] = entry
            record["failures"].pop(domain, None)
            log(f"[{number}/{len(domains)}] {domain}: {entry['records']} captures ({entry['outcome']})")
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        time.sleep(delay)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the requests without sending them")
    args = parser.parse_args()
    domains = [row["domain"] for row in csv.DictReader(DOMAINS.open(encoding="utf-8"))]
    if args.dry_run:
        for domain in domains:
            print(query(domain, showNumPages="true"))
        print(f"{len(domains)} domains; files would be written to {OUTPUT}")
        return
    record = collect(domains, OUTPUT)
    done = sum(domain in record["domains"] for domain in domains)
    print(f"{done}/{len(domains)} domains complete; {len(record['failures'])} failed. Log: {OUTPUT / 'download_record.json'}")
    if record["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
