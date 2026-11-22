"""Select the official-domain allowlist for the final evaluation (reproducible).

Run from ``backend`` after the registry snapshots and historical files are in place:

    python ..\\ml_model\\final_evaluation\\select_official_domains.py

Every candidate comes from an official registry or regulator record that states the
organization's domain or website. Rules, in order:

1. Filter each registry to the agreed sector (see SECTORS below).
2. Reduce each website to its registrable domain with the pinned Public Suffix List.
3. Drop domains listed for more than one organization in their registry, and
   shared platforms (social media, site builders, link pages).
4. Drop every domain that appears in the historical sources of the approved
   protocol (PhishTank snapshot, legitimate archive, Tranco training homepages,
   synthetic fixture).
5. Order the remaining candidates by SHA-256 of "42:<sector>:<domain>" (seed 42 as
   in protocol.json) and keep the first PER_SECTOR per sector.

Nothing here contacts the listed websites; only registry files are read.
"""

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.final_evaluation import (  # noqa: E402
    OFFICIAL_DOMAIN_COLUMNS, canonical_host, is_ip_host, load_historical_index, registrable_domain,
)

REGISTRY = ROOT / "ml_model" / "data" / "final" / "registry"
OUTPUT = ROOT / "ml_model" / "final_evaluation" / "official_domains.csv"
SEED = 42
PER_SECTOR = 20
DOTGOV_COMMIT = "fcdb786528f1a612295565ebd85ee56767ae5e65"
DOTGOV_EVIDENCE = f"https://github.com/cisagov/dotgov-data/blob/{DOTGOV_COMMIT}/current-full.csv"
ACNC_EVIDENCE = ("https://data.gov.au/data/dataset/b050b242-4487-4306-abf5-07ca073e5594/resource/"
                 "8fb32972-24e9-4c95-885e-7140be51be8a (ACNC Register of Australian charities)")
FDIC_EVIDENCE = "https://api.fdic.gov/banks/institutions?filters=CERT:{cert}&fields=NAME,WEBADDR,ACTIVE"
PLATFORMS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "google.com",
    "wixsite.com", "wix.com", "squarespace.com", "wordpress.com", "weebly.com", "blogspot.com", "linktr.ee",
    "gofundme.com", "mailchimp.com", "eventbrite.com", "sites.google.com", "jimdofree.com", "webs.com",
}


def domain_of(website):
    text = (website or "").strip().lower()
    if not text or " " in text:
        return None
    if "://" not in text:
        text = "http://" + text
    host = canonical_host(text.split("://", 1)[1].split("/", 1)[0].split("?", 1)[0].split("@")[-1].split(":")[0])
    if not host or "." not in host or is_ip_host(host):
        return None
    domain = registrable_domain(host)
    return None if domain in PLATFORMS or "." not in domain else domain


def dotgov_candidates():
    rows = list(csv.DictReader((REGISTRY / "dotgov_current-full.csv").open(encoding="utf-8")))
    per_domain = Counter(row["Domain name"].lower() for row in rows)
    out = []
    for row in rows:
        domain = row["Domain name"].strip().lower()
        kind, org, sub = row["Domain type"], row["Organization name"], row["Suborganization name"] or ""
        text = f"{org} {sub}".lower()
        sector = None
        if kind == "State or territory":
            sector = "government"
        elif kind == "School district":
            sector = "education"
        elif kind.startswith("Federal") and "health and human services" in text:
            sector = "health"
        elif kind == "Special district" and any(word in text for word in ("hospital", "health")):
            sector = "health"
        elif kind.startswith("Federal") and "department of transportation" in text:
            sector = "transport_utilities"
        elif kind == "Special district" and any(word in text for word in ("transit", "transportation", "water", "utility", "utilities", "port authority", "airport", "electric")):
            sector = "transport_utilities"
        if sector and per_domain[domain] == 1 and registrable_domain(domain) == domain:
            name = f"{org} - {sub}" if sub and sub != org else org
            out.append((sector, domain, name, "US", DOTGOV_EVIDENCE))
    return out


def acnc_candidates():
    rows = list(csv.DictReader((REGISTRY / "acnc_datadotgov_main.csv").open(encoding="utf-8-sig", errors="replace")))
    domains = [(row, domain_of(row.get("Charity_Website"))) for row in rows]
    per_domain = Counter(domain for _, domain in domains if domain)
    out = []
    for row, domain in domains:
        if not domain or per_domain[domain] != 1 or row.get("Charity_Size") != "Large":
            continue
        if row.get("Advancing_Education") == "Y" and domain.endswith(".edu.au"):
            sector = "education"
        elif row.get("Advancing_Health") == "Y" and row.get("Advancing_Education") != "Y":
            sector = "health"
        elif row.get("Advancing_Education") != "Y" and row.get("Advancing_Health") != "Y":
            sector = "non_profit"
        else:
            continue
        out.append((sector, domain, f"{row['Charity_Legal_Name'].strip()} (ABN {row['ABN']})", "AU", ACNC_EVIDENCE))
    return out


def fdic_candidates():
    data = json.loads((REGISTRY / "fdic_institutions.json").read_text(encoding="utf-8"))["data"]
    banks = [item["data"] for item in data]
    domains = [(bank, domain_of(bank.get("WEBADDR"))) for bank in banks]
    per_domain = Counter(domain for _, domain in domains if domain)
    return [
        ("finance", domain, f"{bank['NAME']} (FDIC cert {bank['CERT']})", "US", FDIC_EVIDENCE.format(cert=bank["CERT"]))
        for bank, domain in domains
        if domain and per_domain[domain] == 1 and 1_000_000 <= (bank.get("ASSET") or 0) <= 50_000_000
    ]


def main(manifest):
    index = load_historical_index(manifest)
    seen = set(index.domain_sources)
    candidates = dotgov_candidates() + acnc_candidates() + fdic_candidates()
    by_sector, report = defaultdict(dict), defaultdict(Counter)
    for sector, domain, name, country, evidence in candidates:
        report[sector]["candidates"] += 1
        if domain in seen:
            report[sector]["seen_in_history"] += 1
            continue
        by_sector[sector].setdefault(domain, (name, country, evidence))
    rows = []
    today = date.today().isoformat()
    for sector in sorted(by_sector):
        ranked = sorted(by_sector[sector], key=lambda d: hashlib.sha256(f"{SEED}:{sector}:{d}".encode()).hexdigest())
        report[sector]["usable_after_history"] = len(ranked)
        for domain in ranked[:PER_SECTOR]:
            name, country, evidence = by_sector[sector][domain]
            rows.append([domain, name, sector, country, evidence, today])
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(OFFICIAL_DOMAIN_COLUMNS)
        writer.writerows(rows)
    print(json.dumps({"selected": len(rows), "by_sector": {s: dict(c) for s, c in report.items()}}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "ml_model" / "final_evaluation" / "historical_sources.json")
