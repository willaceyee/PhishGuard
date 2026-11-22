"""Download Common Crawl URL-index records for the official-domain list.

Run from ``backend`` only after collection is authorized:

    python ..\\ml_model\\final_evaluation\\fetch_cc_index.py            # download
    python ..\\ml_model\\final_evaluation\\fetch_cc_index.py --dry-run  # list requests only

For each domain in official_domains.csv this asks Common Crawl's public index server
for every capture of that domain and its subdomains in CC-MAIN-2026-43 that returned
HTTP 200 with an HTML type. It reads index records only (URL, capture time, status,
MIME type); it never contacts the listed websites. Each domain is saved as one JSON
Lines file in ml_model/data/final/raw/cc-index/, and download_record.json records
every request, its time, and each file's SHA-256. Existing files are kept, so an
interrupted run can be resumed.
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

try:
    # Use certifi's current CA bundle when installed: some Windows certificate stores
    # hold an expired root that makes verification fail. Verification stays on.
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def query(domain, **extra):
    params = [("url", domain), ("matchType", "domain"), ("output", "json"), ("fl", FIELDS),
              ("filter", "status:200"), ("filter", "~mime-detected:html"), *extra.items()]
    return f"{INDEX}?{urllib.parse.urlencode(params)}"


def fetch(url, attempts=5):
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code == 404:  # no captures for this domain
                return ""
            if error.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
        time.sleep(DELAY_SECONDS * 2 ** (attempt + 1))
    return ""


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
    OUTPUT.mkdir(parents=True, exist_ok=True)
    record_path = OUTPUT / "download_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {
        "index": INDEX, "fields": FIELDS, "filters": ["status:200", "~mime-detected:html"],
        "official_domains_sha256": hashlib.sha256(DOMAINS.read_bytes()).hexdigest(), "domains": {},
    }
    for number, domain in enumerate(domains, start=1):
        target = OUTPUT / f"{domain}.jsonl"
        if target.exists() and domain in record["domains"]:
            continue
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pages_text = fetch(query(domain, showNumPages="true"))
        pages = json.loads(pages_text).get("pages", 0) if pages_text.strip() else 0
        lines = []
        for page in range(pages):
            time.sleep(DELAY_SECONDS)
            lines += [line for line in fetch(query(domain, page=str(page))).splitlines() if line.strip()]
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        record["domains"][domain] = {
            "requested_at_utc": started, "pages": pages, "records": len(lines),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"[{number}/{len(domains)}] {domain}: {len(lines)} captures")
        time.sleep(DELAY_SECONDS)
    print(f"Done. Files in {OUTPUT}; request log in {record_path}")


if __name__ == "__main__":
    main()
