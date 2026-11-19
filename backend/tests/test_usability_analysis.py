"""Tests for the usability-results analysis script.

Every participant row in this file is a SYNTHETIC TEST FIXTURE. The codes use a
``SYN-`` prefix and the values were chosen only to exercise the calculations.
They are not participant data and must never be reported as study results.
"""

import csv
import json
from pathlib import Path

import pytest

from scripts import analyze_usability as usability


TEMPLATE = Path(__file__).resolve().parents[2] / "docs" / "usability_results_template.csv"
COLUMNS = usability.REQUIRED_COLUMNS
SYNTHETIC_COMMENT = "SYNTHETIC TEST FIXTURE"


def synthetic_task(code, role, task_id, outcome, seconds, errors, assistance):
    return {
        "participant_code": code,
        "participant_role": role,
        "task_id": task_id,
        "outcome": outcome,
        "completion_seconds": seconds,
        "error_count": errors,
        "assistance_required": assistance,
    }


def synthetic_questionnaire(code, role, consent, ratings):
    row = {
        "participant_code": code,
        "participant_role": role,
        "consent_confirmed": consent,
        "task_id": "QUESTIONNAIRE",
        "anonymous_comment": SYNTHETIC_COMMENT,
    }
    row.update(zip(usability.RATING_COLUMNS, ratings))
    return row


def write_synthetic_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})
    return path


SYNTHETIC_ROWS = [
    synthetic_task("SYN-A01", "administrator", "A1", "success", "30", "0", "no"),
    synthetic_task("SYN-A01", "administrator", "A2", "success", "50", "1", "no"),
    synthetic_task("SYN-A01", "administrator", "A3", "partial", "120", "2", "yes"),
    synthetic_task("SYN-A01", "administrator", "A4", "failure", "200", "3", "yes"),
    synthetic_questionnaire("SYN-A01", "administrator", "yes", ["4", "5", "4", "3", "4", "5"]),
    synthetic_task("SYN-A02", "administrator", "A1", "success", "40", "0", "no"),
    synthetic_task("SYN-A02", "administrator", "A2", "success", "90", "0", "no"),
    synthetic_questionnaire("SYN-A02", "administrator", "yes", ["5", "4", "4", "4", "5", "4"]),
    synthetic_task("SYN-E01", "end_user", "E1", "success", "20", "0", "no"),
    synthetic_task("SYN-E01", "end_user", "E2", "partial", "60", "1", "yes"),
    synthetic_task("SYN-E01", "end_user", "E3", "success", "", "0", "no"),
    synthetic_task("SYN-E01", "end_user", "E4", "", "", "", ""),
    synthetic_questionnaire("SYN-E01", "end_user", "yes", ["3", "4", "5", "4", "3", ""]),
    synthetic_task("SYN-E02", "end_user", "E1", "success", "10", "0", "no"),
    synthetic_questionnaire("SYN-E02", "end_user", "no", ["1", "1", "1", "1", "1", "1"]),
    {},
]


@pytest.fixture
def synthetic_csv(tmp_path):
    return write_synthetic_csv(tmp_path / "synthetic_usability_results.csv", SYNTHETIC_ROWS)


def test_blank_template_produces_no_results():
    summary = usability.analyze(TEMPLATE)

    assert summary["combined"]["participants"] == 0
    assert summary["combined"]["attempted_tasks"] == 0
    assert summary["combined"]["success_percentage"] is None
    assert summary["combined"]["median_success_seconds"] is None
    assert all(item.endswith("consent not confirmed") for item in summary["excluded_participants"])
    assert "nothing to analyze" in usability.format_summary(summary)


def test_synthetic_results_are_grouped_by_role(synthetic_csv):
    summary = usability.analyze(synthetic_csv)
    admin = summary["roles"]["administrator"]
    end_user = summary["roles"]["end_user"]
    combined = summary["combined"]

    assert summary["excluded_participants"] == ["SYN-E02: consent not confirmed"]
    assert summary["blank_lines_ignored"] == 1

    assert admin["participants"] == 2
    assert admin["outcomes"] == {"success": 4, "partial": 1, "failure": 1}
    assert admin["success_percentage"] == 66.7
    assert admin["median_success_seconds"] == 45.0
    assert (admin["error_total"], admin["assistance_total"]) == (6, 2)
    assert admin["mean_ratings"]["ease_rating"] == {"mean": 4.5, "responses": 2}
    assert admin["mean_ratings"]["readability_rating"]["mean"] == 3.5

    assert end_user["outcomes"] == {"success": 2, "partial": 1, "failure": 0}
    assert end_user["tasks_not_recorded"] == 1
    assert end_user["median_success_seconds"] == 20.0
    assert end_user["success_times_used"] == 1
    assert end_user["incomplete_task_rows"] == ["SYN-E01 E3: blank completion_seconds"]
    assert end_user["mean_ratings"]["overall_satisfaction_rating"] == {
        "mean": None,
        "responses": 0,
    }

    assert combined["participants"] == 3
    assert combined["attempted_tasks"] == 9
    assert combined["success_percentage"] == 66.7
    assert combined["median_success_seconds"] == 40.0
    assert (combined["error_total"], combined["assistance_total"]) == (7, 3)
    assert combined["mean_ratings"]["ease_rating"]["mean"] == 4.0
    assert combined["mean_ratings"]["overall_satisfaction_rating"] == {
        "mean": 4.5,
        "responses": 2,
    }


def test_participant_without_questionnaire_is_excluded(tmp_path):
    path = write_synthetic_csv(
        tmp_path / "synthetic.csv",
        [synthetic_task("SYN-A09", "administrator", "A1", "success", "30", "0", "no")],
    )

    summary = usability.analyze(path)

    assert summary["excluded_participants"] == ["SYN-A09: no QUESTIONNAIRE row"]
    assert summary["combined"]["attempted_tasks"] == 0


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (synthetic_task("SYN-A01", "manager", "A1", "success", "1", "0", "no"), "unknown participant_role"),
        (synthetic_task("SYN-A01", "administrator", "E1", "success", "1", "0", "no"), "not a administrator task"),
        (synthetic_task("SYN-A01", "administrator", "A1", "done", "1", "0", "no"), "outcome must be"),
        (synthetic_task("SYN-A01", "administrator", "A1", "success", "-5", "0", "no"), "completion_seconds must be"),
        (synthetic_task("SYN-A01", "administrator", "A1", "success", "1", "two", "no"), "error_count must be a number"),
        (synthetic_task("SYN-A01", "administrator", "A1", "partial", "1", "0", "maybe"), "assistance_required must be"),
        (synthetic_task("SYN-A01", "administrator", "A1", "success", "1", "0", "yes"), "recorded as partial"),
        (synthetic_task("", "administrator", "A1", "success", "1", "0", "no"), "participant_code is blank"),
        (synthetic_questionnaire("SYN-A01", "administrator", "yes", ["6"]), "ease_rating must be 1-5"),
    ],
)
def test_invalid_values_are_reported_with_line_numbers(tmp_path, row, message):
    path = write_synthetic_csv(tmp_path / "synthetic.csv", [row])

    with pytest.raises(usability.UsabilityDataError) as error:
        usability.analyze(path)

    assert "line 2" in str(error.value)
    assert message in str(error.value)


def test_duplicates_and_conflicting_roles_are_rejected(tmp_path):
    task = synthetic_task("SYN-A01", "administrator", "A1", "success", "1", "0", "no")
    questionnaire = synthetic_questionnaire("SYN-A01", "administrator", "yes", [])
    conflict = synthetic_task("SYN-A01", "end_user", "E1", "success", "1", "0", "no")
    path = write_synthetic_csv(
        tmp_path / "synthetic.csv", [task, task, questionnaire, questionnaire, conflict]
    )

    with pytest.raises(usability.UsabilityDataError) as error:
        usability.analyze(path)

    assert error.value.problems == [
        "line 3: duplicate task A1 for SYN-A01",
        "line 5: duplicate QUESTIONNAIRE row for SYN-A01",
        "line 6: SYN-A01 has conflicting roles",
    ]


def test_missing_columns_are_rejected(tmp_path):
    path = tmp_path / "synthetic.csv"
    path.write_text("participant_code,task_id\nSYN-A01,A1\n", encoding="utf-8")

    with pytest.raises(usability.UsabilityDataError, match="missing columns"):
        usability.analyze(path)


def test_command_line_text_and_json_output(synthetic_csv, capsys):
    assert usability.main([str(synthetic_csv)]) == 0
    text = capsys.readouterr().out
    assert "[administrator]" in text
    assert "Successful-task completion: 66.7%" in text
    assert "SYN-E02: consent not confirmed" in text

    assert usability.main([str(synthetic_csv), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["combined"]["attempted_tasks"] == 9


def test_command_line_reports_invalid_data(tmp_path, capsys):
    path = write_synthetic_csv(
        tmp_path / "synthetic.csv",
        [synthetic_task("SYN-A01", "administrator", "A1", "done", "1", "0", "no")],
    )

    assert usability.main([str(path)]) == 1
    assert "outcome must be" in capsys.readouterr().err
