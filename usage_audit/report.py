"""Render a report dict as Markdown or JSON."""

from __future__ import annotations

import json


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    add = lines.append
    add("# usage-audit report")
    add("")
    add(f"version: {report['version']}")
    if report["inputs"]:
        for item in report["inputs"]:
            add(f"input: {item['path']} ({item['format']})")
    else:
        add("input: (none)")
    add(f"rows read: {report['rows_read']}")
    add(f"rows used: {report['rows_used']}")
    add(f"rows outside window: {report['rows_outside_window']}")
    add(f"malformed rows: {report['malformed']}")
    add(f"rows missing units: {report['rows_missing_units']}")
    add(f"rows with unreadable units: {report['rows_unreadable_units']}")
    add(f"file span: {report['file_span']['text']}")
    add(f"input window: {report['window']['text']}")
    filt = report["filter"]
    if filt["since"] or filt["until"]:
        add(f"filter since: {filt['since'] or '(none)'}")
        add(f"filter until: {filt['until'] or '(none)'}")
        if filt["since_note"]:
            add(f"since bound: {filt['since_note']}")
    add(f"runs total: {report['runs_total']}")
    add(f"units total: {report['units_total']}")
    add("")
    add(report["notes"]["units"])
    add(report["notes"]["timezone"])
    add(report["notes"]["window"])
    add(report["notes"]["malformed"])
    classes = report["classification"]
    add(
        "Classification: no-op ["
        + ", ".join(classes["noop"])
        + "]; changed ["
        + ", ".join(classes["changed"])
        + "]; error ["
        + ", ".join(classes["error"])
        + "]; schedule triggers ["
        + ", ".join(classes["schedule_triggers"])
        + "]."
    )
    add("")
    _section(lines, "Spend by agent", _spend_table("agent", report["spend"]["by_agent"]))
    _section(lines, "Spend by routine", _spend_table("routine", report["spend"]["by_routine"]))
    _section(lines, "Spend by trigger", _spend_table("trigger", report["spend"]["by_trigger"]))
    _section(lines, "Spend by day", _spend_table("day", report["spend"]["by_day"]))
    _section(lines, "No-op wakes by routine", _noop_table(report["noop_by_routine"]))
    _section(lines, "Schedules", _schedule_block(report))
    _section(lines, "Repeated identical errors", _error_block(report))
    _section(lines, f"Top {report['top']} costliest runs", _top_block(report))
    if report["malformed"]:
        _section(lines, "Malformed rows", _malformed_block(report))
    add("")
    return "\n".join(lines)


def _section(lines: list[str], title: str, body: list[str]) -> None:
    lines.append(f"## {title}")
    lines.append("")
    lines.extend(body)
    lines.append("")


def _spend_table(label: str, rows: list[dict]) -> list[str]:
    return _table(
        [label, "runs", "units", "missing units", "unreadable units"],
        [
            [row["key"], row["runs"], row["units"], row["missing_units"], row["unreadable_units"]]
            for row in rows
        ],
    )


def _noop_table(rows: list[dict]) -> list[str]:
    intro = (
        "The no-op rate column is no-op runs / runs. "
        "No-op units are the recorded units on those no-op rows only."
    )
    table = _table(
        [
            "routine",
            "runs",
            "no-op runs",
            "no-op rate",
            "no-op units",
            "no-op missing units",
            "no-op unreadable units",
        ],
        [
            [
                row["routine"],
                row["runs"],
                row["noop_runs"],
                f"{row['noop_runs']}/{row['runs']}",
                row["noop_units"],
                row["noop_missing_units"],
                row["noop_unreadable_units"],
            ]
            for row in rows
        ],
    )
    return [intro, ""] + table


def _schedule_block(report: dict) -> list[str]:
    rows = report["schedules"]
    table = _table(
        [
            "routine",
            "agents",
            "fires",
            "changes",
            "no-ops",
            "errors",
            "other",
            "units",
            "missing units",
            "flagged",
        ],
        [
            [
                row["routine"],
                ", ".join(row["agents"]),
                row["fires"],
                row["changes"],
                row["noops"],
                row["errors"],
                row["other"],
                row["units"],
                row["missing_units"],
                "yes" if row["flagged"] else "no",
            ]
            for row in rows
        ],
    )
    lines = [report["notes"]["schedule_rule"], "", *table, "", report["notes"]["schedule"]]
    for row in rows:
        lines.append(f"- {row['routine']}: {_gap_phrase('fire gaps', row['fire_gaps_seconds'])}")
        lines.append(
            f"- {row['routine']}: {_gap_phrase('change gaps', row['change_gaps_seconds'])}"
        )
    return lines


def _gap_phrase(label: str, gaps: dict | None) -> str:
    if not gaps:
        return f"{label}: fewer than 2 rows."
    return (
        f"{label}: n={gaps['count']} min {gaps['min']} median {gaps['median']} "
        f"max {gaps['max']} seconds."
    )


def _error_block(report: dict) -> list[str]:
    rows = report["repeated_errors"]
    table = _table(
        [
            "agent",
            "routine",
            "error",
            "kind",
            "occurrences",
            "longest streak",
            "units",
            "first",
            "last",
        ],
        [
            [
                row["agent"],
                row["routine"],
                row["error"] or "(no error text)",
                row["kind"],
                row["occurrences"],
                row["longest_streak"],
                row["units"],
                row["first"] or "",
                row["last"] or "",
            ]
            for row in rows
        ],
    )
    return [report["notes"]["retry"], ""] + table


def _top_block(report: dict) -> list[str]:
    shown = len(report["top_runs"])
    recorded = report["rows_with_recorded_units"]
    intro = (
        f"Ranked by recorded units. Rows that do not record a number are omitted, not treated as zero. "
        f"Showing {shown} of {recorded} rows that recorded units."
    )
    table = _table(
        ["units", "timestamp", "agent", "routine", "trigger", "outcome", "duration", "source", "line"],
        [
            [
                row["units"],
                row["timestamp"],
                row["agent"],
                row["routine"],
                row["trigger"],
                row["outcome"],
                row["duration"],
                row["source"],
                row["line"],
            ]
            for row in report["top_runs"]
        ],
    )
    return [intro, ""] + table


def _malformed_block(report: dict) -> list[str]:
    lines = []
    for item in report["malformed_samples"]:
        lines.append(f"- {item['source']}:{item['line']}: {item['reason']}")
    omitted = report["malformed_omitted"]
    if omitted:
        lines.append(f"- and {omitted} more")
    return lines


def _table(headers: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["(none)"]
    rendered = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        rendered.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return rendered


def _cell(value) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text.replace("|", "\\|")
