"""Summarize recorded usability-study results.

Input is a CSV in the format of ``docs/usability_results_template.csv``. The
script only calculates statistics from rows that facilitators have recorded; it
never creates or estimates participant data.

Row handling:

- Participants are included only when their ``QUESTIONNAIRE`` row has
  ``consent_confirmed`` set to ``yes``. Other participants are listed as excluded.
- Task rows with a blank ``outcome`` are counted as not recorded and are not
  treated as attempted.
- Blank time, error, assistance, or rating cells are left out of the matching
  statistic, and the number of values used is reported alongside it.
- Invalid values (unknown roles, task IDs, outcomes, out-of-range ratings,
  duplicates, conflicting roles, or ``success`` recorded with assistance) stop
  the analysis with line numbers so the
  data can be corrected rather than silently skipped.

Run from ``backend``::

    .\\venv\\Scripts\\python.exe -m scripts.analyze_usability path\\to\\results.csv
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path


REQUIRED_COLUMNS = (
    "participant_code",
    "participant_role",
    "consent_confirmed",
    "task_id",
    "outcome",
    "completion_seconds",
    "error_count",
    "assistance_required",
    "ease_rating",
    "clarity_rating",
    "explanation_helpfulness_rating",
    "readability_rating",
    "confidence_rating",
    "overall_satisfaction_rating",
    "anonymous_comment",
)
RATING_COLUMNS = REQUIRED_COLUMNS[8:14]
ROLE_TASKS = {
    "administrator": {f"A{number}" for number in range(1, 8)},
    "end_user": {f"E{number}" for number in range(1, 5)},
}
ROLES = tuple(ROLE_TASKS)
QUESTIONNAIRE = "QUESTIONNAIRE"
OUTCOMES = ("success", "partial", "failure")
YES_NO = {"yes": True, "no": False}


class UsabilityDataError(ValueError):
    """Raised when recorded values are invalid and must be corrected."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("; ".join(problems))


def _cell(row, column):
    return (row.get(column) or "").strip()


def _optional_number(value, line, column, problems, minimum=0, maximum=None, integer=False):
    if value == "":
        return None
    try:
        number = int(value) if integer else float(value)
    except ValueError:
        problems.append(f"line {line}: {column} must be a number, got {value!r}")
        return None
    if number < minimum or (maximum is not None and number > maximum):
        limit = f"{minimum}-{maximum}" if maximum is not None else f">= {minimum}"
        problems.append(f"line {line}: {column} must be {limit}, got {value!r}")
        return None
    return number


def load_rows(csv_path):
    """Read and validate the results CSV, returning parsed participant data."""
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or ())]
        if missing:
            raise UsabilityDataError([f"missing columns: {', '.join(missing)}"])
        raw_rows = list(enumerate(reader, start=2))

    problems = []
    participants = {}
    blank_lines = 0
    for line, row in raw_rows:
        if not any(_cell(row, column) for column in REQUIRED_COLUMNS):
            blank_lines += 1
            continue
        code = _cell(row, "participant_code")
        role = _cell(row, "participant_role").lower()
        task_id = _cell(row, "task_id").upper()
        if not code:
            problems.append(f"line {line}: participant_code is blank")
            continue
        if role not in ROLE_TASKS:
            problems.append(f"line {line}: unknown participant_role {role!r}")
            continue
        participant = participants.setdefault(
            code, {"role": role, "consent": None, "tasks": {}, "ratings": None}
        )
        if participant["role"] != role:
            problems.append(f"line {line}: {code} has conflicting roles")
            continue

        if task_id == QUESTIONNAIRE:
            if participant["ratings"] is not None:
                problems.append(f"line {line}: duplicate QUESTIONNAIRE row for {code}")
                continue
            consent = _cell(row, "consent_confirmed").lower()
            if consent not in ("", "yes", "no"):
                problems.append(f"line {line}: consent_confirmed must be yes, no, or blank")
            participant["consent"] = consent == "yes"
            participant["ratings"] = {
                column: _optional_number(
                    _cell(row, column), line, column, problems, 1, 5, integer=True
                )
                for column in RATING_COLUMNS
            }
            continue

        if task_id not in ROLE_TASKS[role]:
            problems.append(f"line {line}: task {task_id!r} is not a {role} task")
            continue
        if task_id in participant["tasks"]:
            problems.append(f"line {line}: duplicate task {task_id} for {code}")
            continue
        outcome = _cell(row, "outcome").lower()
        if outcome not in ("", *OUTCOMES):
            problems.append(f"line {line}: outcome must be success, partial, or failure")
            continue
        assistance = _cell(row, "assistance_required").lower()
        if assistance not in ("", *YES_NO):
            problems.append(f"line {line}: assistance_required must be yes, no, or blank")
            assistance = ""
        if outcome == "success" and assistance == "yes":
            # The testing guide defines success as completion without intervention.
            problems.append(f"line {line}: success with assistance must be recorded as partial")
            continue
        participant["tasks"][task_id] = {
            "line": line,
            "outcome": outcome or None,
            "seconds": _optional_number(
                _cell(row, "completion_seconds"), line, "completion_seconds", problems
            ),
            "errors": _optional_number(
                _cell(row, "error_count"), line, "error_count", problems, integer=True
            ),
            "assistance": YES_NO.get(assistance),
        }

    if problems:
        raise UsabilityDataError(problems)
    return participants, blank_lines


def _rounded(value, digits):
    return None if value is None else round(value, digits)


def summarize_group(participants):
    """Calculate statistics for a list of included participant records."""
    counts = dict.fromkeys(OUTCOMES, 0)
    success_times = []
    errors = []
    assistance = []
    not_recorded = 0
    incomplete = []
    for participant in participants:
        for task_id, task in sorted(participant["tasks"].items()):
            if task["outcome"] is None:
                not_recorded += 1
                continue
            counts[task["outcome"]] += 1
            missing = [
                name
                for name, value in (
                    ("completion_seconds", task["seconds"]),
                    ("error_count", task["errors"]),
                    ("assistance_required", task["assistance"]),
                )
                if value is None
            ]
            if missing:
                incomplete.append(f"{participant['code']} {task_id}: blank {', '.join(missing)}")
            if task["outcome"] == "success" and task["seconds"] is not None:
                success_times.append(task["seconds"])
            if task["errors"] is not None:
                errors.append(task["errors"])
            if task["assistance"] is not None:
                assistance.append(task["assistance"])

    attempted = sum(counts.values())
    ratings = {}
    for column in RATING_COLUMNS:
        values = [
            participant["ratings"][column]
            for participant in participants
            if participant["ratings"][column] is not None
        ]
        ratings[column] = {
            "mean": _rounded(statistics.mean(values), 2) if values else None,
            "responses": len(values),
        }
    return {
        "participants": len(participants),
        "attempted_tasks": attempted,
        "outcomes": counts,
        "success_percentage": (
            round(100 * counts["success"] / attempted, 1) if attempted else None
        ),
        "median_success_seconds": (
            _rounded(statistics.median(success_times), 1) if success_times else None
        ),
        "success_times_used": len(success_times),
        "error_total": sum(errors),
        "error_values_used": len(errors),
        "assistance_total": sum(assistance),
        "assistance_values_used": len(assistance),
        "mean_ratings": ratings,
        "tasks_not_recorded": not_recorded,
        "incomplete_task_rows": incomplete,
    }


def analyze(csv_path):
    """Return a role-grouped and combined summary of recorded results."""
    participants, blank_lines = load_rows(csv_path)
    included = {role: [] for role in ROLES}
    excluded = []
    for code, participant in sorted(participants.items()):
        participant["code"] = code
        if participant["ratings"] is None:
            excluded.append(f"{code}: no QUESTIONNAIRE row")
        elif not participant["consent"]:
            excluded.append(f"{code}: consent not confirmed")
        else:
            included[participant["role"]].append(participant)
    return {
        "source": str(csv_path),
        "blank_lines_ignored": blank_lines,
        "excluded_participants": excluded,
        "roles": {role: summarize_group(group) for role, group in included.items()},
        "combined": summarize_group([p for group in included.values() for p in group]),
    }


def _show(value, suffix=""):
    return "n/a" if value is None else f"{value}{suffix}"


def format_summary(summary):
    lines = [f"Usability results: {summary['source']}"]
    if summary["excluded_participants"]:
        lines.append("Excluded participants:")
        lines.extend(f"  - {item}" for item in summary["excluded_participants"])
    sections = [*summary["roles"].items(), ("combined", summary["combined"])]
    for name, group in sections:
        outcomes = group["outcomes"]
        lines += [
            "",
            f"[{name}]",
            f"  Participants: {group['participants']}",
            f"  Attempted tasks: {group['attempted_tasks']} "
            f"(not recorded: {group['tasks_not_recorded']})",
            f"  Success / partial / failure: {outcomes['success']} / "
            f"{outcomes['partial']} / {outcomes['failure']}",
            f"  Successful-task completion: {_show(group['success_percentage'], '%')}",
            f"  Median successful-task time: "
            f"{_show(group['median_success_seconds'], ' s')} "
            f"(n={group['success_times_used']})",
            f"  Errors total: {group['error_total']} (n={group['error_values_used']})",
            f"  Assistance total: {group['assistance_total']} "
            f"(n={group['assistance_values_used']})",
            "  Mean ratings:",
        ]
        for column, rating in group["mean_ratings"].items():
            lines.append(
                f"    {column}: {_show(rating['mean'])} (n={rating['responses']})"
            )
        if group["incomplete_task_rows"] and name != "combined":
            lines.append("  Incomplete task rows:")
            lines.extend(f"    - {item}" for item in group["incomplete_task_rows"])
    if summary["combined"]["participants"] == 0:
        lines += ["", "No participants with confirmed consent; nothing to analyze."]
    elif summary["combined"]["attempted_tasks"] == 0:
        lines += ["", "No task outcomes have been recorded yet."]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize recorded usability results.")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    try:
        summary = analyze(args.csv_path)
    except UsabilityDataError as error:
        print("Invalid usability results:", file=sys.stderr)
        for problem in error.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2) if args.json else format_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
