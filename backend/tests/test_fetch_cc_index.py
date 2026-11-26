"""Resume and outcome rules of ml_model/final_evaluation/fetch_cc_index.py (no network)."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ml_model" / "final_evaluation" / "fetch_cc_index.py"
spec = importlib.util.spec_from_file_location("fetch_cc_index", SCRIPT)
fetch_cc_index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_cc_index)

HTML = {"status": "200", "mime-detected": "text/html"}


class FakeServer:
    """Answers index queries from a dict: domain -> list of pages (each a list of rows), or
    None for a 404, or an exception to raise."""

    def __init__(self, data):
        self.data, self.calls = data, []

    def __call__(self, url):
        self.calls.append(url)
        domain = next(part.split("=", 1)[1] for part in url.split("?", 1)[1].split("&") if part.startswith("url="))
        value = self.data[domain]
        if isinstance(value, Exception):
            raise value
        if value is None:
            return None
        if "showNumPages=true" in url:
            return json.dumps({"pages": len(value)})
        page = int(url.rsplit("page=", 1)[1])
        return "\n".join(json.dumps({"url": f"https://{domain}/{n}", **row}) for n, row in enumerate(value[page]))


def run(tmp_path, server, domains):
    return fetch_cc_index.collect(domains, tmp_path, fetcher=server, delay=0, log=lambda _: None)


def test_query_uses_corrected_filters():
    url = fetch_cc_index.query("example.gov")
    assert "filter=status%3A200" in url
    assert "filter=%3Dmime-detected%3Atext%2Fhtml" in url
    assert "~mime-detected" not in url and "%7Emime-detected" not in url


def test_captured_and_no_capture_outcomes_are_distinct(tmp_path):
    server = FakeServer({"a.gov": [[HTML, HTML], [HTML]], "b.gov": None})
    record = run(tmp_path, server, ["a.gov", "b.gov"])
    a, b = record["domains"]["a.gov"], record["domains"]["b.gov"]
    assert (a["outcome"], a["records"], a["pages"]) == ("captured", 3, 2)
    assert (b["outcome"], b["records"], b["pages"]) == ("no_matching_captures", 0, 0)
    assert a["filters"] == b["filters"] == fetch_cc_index.FILTERS
    assert record["failures"] == {}
    assert (tmp_path / "b.gov.jsonl").read_text(encoding="utf-8") == ""


def test_failed_request_writes_no_file_and_is_retried(tmp_path):
    server = FakeServer({"a.gov": OSError("gateway time-out")})
    record = run(tmp_path, server, ["a.gov"])
    assert "a.gov" not in record["domains"]
    assert "OSError" in record["failures"]["a.gov"]["error"]
    assert not (tmp_path / "a.gov.jsonl").exists()

    server.data["a.gov"] = [[HTML]]
    record = run(tmp_path, server, ["a.gov"])
    assert record["domains"]["a.gov"]["outcome"] == "captured"
    assert record["failures"] == {}


def test_resume_skips_only_complete_entries_with_current_filters(tmp_path):
    server = FakeServer({"a.gov": [[HTML]], "b.gov": [[HTML]]})
    run(tmp_path, server, ["a.gov", "b.gov"])
    log_path = tmp_path / "download_record.json"
    record = json.loads(log_path.read_text(encoding="utf-8"))
    del record["domains"]["b.gov"]["filters"]  # entry made by an older version of the script
    log_path.write_text(json.dumps(record), encoding="utf-8")

    server.calls.clear()
    record = run(tmp_path, server, ["a.gov", "b.gov"])
    fetched = {call.split("url=", 1)[1].split("&", 1)[0] for call in server.calls}
    assert fetched == {"b.gov"}
    assert record["domains"]["b.gov"]["filters"] == fetch_cc_index.FILTERS


def test_changed_file_is_fetched_again(tmp_path):
    server = FakeServer({"a.gov": [[HTML]]})
    run(tmp_path, server, ["a.gov"])
    (tmp_path / "a.gov.jsonl").write_text("tampered\n", encoding="utf-8")
    server.calls.clear()
    run(tmp_path, server, ["a.gov"])
    assert server.calls


def test_log_made_with_other_filters_is_refused(tmp_path):
    (tmp_path / "download_record.json").write_text(
        json.dumps({"filters": ["status:200", "~mime-detected:html"], "domains": {}}), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="move that folder aside"):
        run(tmp_path, FakeServer({}), ["a.gov"])


def test_rows_outside_the_filters_fail_the_domain(tmp_path):
    server = FakeServer({"a.gov": [[HTML, {"status": "200", "mime-detected": "application/pdf"}]]})
    record = run(tmp_path, server, ["a.gov"])
    assert "a.gov" in record["failures"] and "a.gov" not in record["domains"]
