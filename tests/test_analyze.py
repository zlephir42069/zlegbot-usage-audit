"""Hand-computed totals. Missing units stay missing."""

from decimal import Decimal

from usage_audit.analyze import SUGGESTION, UNITS_NOTE, build_report
from usage_audit.config import default_config
from usage_audit.load import load_logs

from conftest import SAMPLE_CSV, SAMPLE_JSONL


def _report(path=SAMPLE_JSONL, **kwargs):
    loaded = load_logs([str(path)], default_config())
    return build_report(loaded, default_config(), **kwargs)


def _by_key(rows):
    return {row["key"]: row for row in rows}


def test_sample_totals_are_sums_of_the_file():
    report = _report()
    assert report["rows_read"] == 10
    assert report["rows_used"] == 10
    assert report["malformed"] == 0
    assert report["rows_missing_units"] == 0
    assert report["rows_unreadable_units"] == 0
    assert report["units_total"] == "1850"
    assert report["runs_total"] == 10
    assert report["window"]["text"] == "2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z"
    assert report["file_span"]["text"] == report["window"]["text"]
    assert report["filter"]["since"] is None

    agents = _by_key(report["spend"]["by_agent"])
    assert agents["digest-bot"]["runs"] == 4
    assert agents["digest-bot"]["units"] == "1230"
    assert agents["inbox-bot"]["runs"] == 6
    assert agents["inbox-bot"]["units"] == "620"
    assert [row["key"] for row in report["spend"]["by_agent"]] == ["digest-bot", "inbox-bot"]

    routines = _by_key(report["spend"]["by_routine"])
    assert routines["daily-digest"]["units"] == "1230"
    assert routines["poll-inbox"]["units"] == "620"

    triggers = _by_key(report["spend"]["by_trigger"])
    assert triggers["schedule"] == {
        "key": "schedule",
        "runs": 8,
        "units": "1710",
        "missing_units": 0,
        "unreadable_units": 0,
    }
    assert triggers["manual"]["units"] == "90"
    assert triggers["event"]["units"] == "50"

    days = report["spend"]["by_day"]
    assert [row["key"] for row in days] == ["2026-10-01", "2026-10-02"]
    assert days[0]["runs"] == 7
    assert days[0]["units"] == "1650"
    assert days[1]["runs"] == 3
    assert days[1]["units"] == "200"

    grouped = {row["key"]: Decimal(row["units"]) for row in report["spend"]["by_agent"]}
    assert sum(grouped.values(), Decimal(0)) == Decimal(report["units_total"])
    assert sum(Decimal(row["units"]) for row in days) == Decimal("1850")


def test_sample_noop_schedule_retry_and_top():
    report = _report()
    noop = {row["routine"]: row for row in report["noop_by_routine"]}
    assert noop["poll-inbox"]["runs"] == 6
    assert noop["poll-inbox"]["noop_runs"] == 3
    assert noop["poll-inbox"]["noop_units"] == "300"
    assert noop["daily-digest"]["runs"] == 4
    assert noop["daily-digest"]["noop_runs"] == 1
    assert noop["daily-digest"]["noop_units"] == "10"

    schedules = {row["routine"]: row for row in report["schedules"]}
    poll = schedules["poll-inbox"]
    assert poll["fires"] == 4
    assert poll["changes"] == 1
    assert poll["noops"] == 3
    assert poll["errors"] == 0
    assert poll["units"] == "480"
    assert poll["flagged"] is True
    assert poll["agents"] == ["inbox-bot"]
    assert poll["fire_gaps_seconds"] == {
        "count": 3,
        "min": "900",
        "median": "900",
        "max": "84600",
    }
    assert poll["change_gaps_seconds"] is None
    digest = schedules["daily-digest"]
    assert digest["fires"] == 4
    assert digest["changes"] == 1
    assert digest["noops"] == 1
    assert digest["errors"] == 2
    assert digest["units"] == "1230"
    assert digest["flagged"] is True
    assert digest["fire_gaps_seconds"]["min"] == "300"
    assert digest["fire_gaps_seconds"]["median"] == "300"
    assert digest["fire_gaps_seconds"]["max"] == "121800"
    assert report["notes"]["schedule"] == SUGGESTION

    assert report["repeated_errors"] == [
        {
            "agent": "digest-bot",
            "routine": "daily-digest",
            "error": "upstream timeout",
            "kind": "retry loop",
            "occurrences": 2,
            "longest_streak": 2,
            "units": "800",
            "missing_units": 0,
            "unreadable_units": 0,
            "first": "2026-10-01T02:00:00Z",
            "last": "2026-10-01T02:05:00Z",
        }
    ]

    top = report["top_runs"]
    assert [row["units"] for row in top] == [
        "420",
        "400",
        "400",
        "180",
        "100",
        "100",
        "100",
        "90",
        "50",
        "10",
    ]
    assert top[0]["line"] == 8
    assert top[0]["routine"] == "daily-digest"
    assert top[0]["duration"] == "8"
    assert top[1]["timestamp"] == "2026-10-01T02:05:00Z"
    assert top[2]["timestamp"] == "2026-10-01T02:00:00Z"
    assert [row["timestamp"] for row in top if row["units"] == "100"] == [
        "2026-10-02T00:00:00Z",
        "2026-10-01T00:15:00Z",
        "2026-10-01T00:00:00Z",
    ]


def test_csv_sample_matches_jsonl_totals():
    jsonl = _report(SAMPLE_JSONL)
    csv = _report(SAMPLE_CSV)
    assert csv["units_total"] == jsonl["units_total"]
    assert csv["spend"] == jsonl["spend"]
    assert csv["noop_by_routine"] == jsonl["noop_by_routine"]
    assert csv["repeated_errors"] == jsonl["repeated_errors"]
    assert [row["units"] for row in csv["top_runs"]] == [row["units"] for row in jsonl["top_runs"]]
    assert csv["inputs"][0]["format"] == "csv"
    assert jsonl["inputs"][0]["format"] == "jsonl"


def test_missing_units_are_not_filled_in(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-10-01T00:00:00Z","agent":"a","trigger":"schedule","routine":"r","outcome":"no-op"}',
                '{"timestamp":"2026-10-01T01:00:00Z","agent":"a","trigger":"schedule","routine":"r","units":5,"outcome":"no-op"}',
                '{"timestamp":"2026-10-01T02:00:00Z","agent":"a","trigger":"schedule","routine":"r","units":"n/a","outcome":"changed"}',
                '{"timestamp":"2026-10-01T03:00:00Z","agent":"a","trigger":"manual","routine":"r","units":0,"outcome":"changed"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = _report(path)
    assert report["units_total"] == "5"
    assert report["rows_missing_units"] == 1
    assert report["rows_unreadable_units"] == 1
    assert report["runs_total"] == 4
    noop = report["noop_by_routine"][0]
    assert noop["noop_runs"] == 2
    assert noop["noop_units"] == "5"
    assert noop["noop_missing_units"] == 1
    schedule = report["schedules"][0]
    assert schedule["fires"] == 3
    assert schedule["changes"] == 1
    assert schedule["units"] == "5"
    assert schedule["missing_units"] == 1
    assert schedule["unreadable_units"] == 1
    assert schedule["flagged"] is True
    assert [row["units"] for row in report["top_runs"]] == ["5", "0"]
    assert "estimat" not in UNITS_NOTE.lower()


def test_repeated_errors_split_streaks(tmp_path):
    path = tmp_path / "runs.jsonl"
    rows = [
        ("00:00", "error", "Timeout", "2"),
        ("00:01", "error", "timeout", "2"),
        ("00:02", "changed", "", "9"),
        ("00:03", "error", "timeout", "2"),
        ("00:04", "error", "other", "4"),
        ("00:05", "changed", "", "1"),
        ("00:06", "error", "other", "4"),
        ("00:07", "error", "once", "7"),
    ]
    lines = []
    for stamp, outcome, error, units in rows:
        lines.append(
            "{"
            f'"timestamp":"2026-10-01T{stamp}:00Z",'
            '"agent":"Bot","routine":"job","trigger":"event",'
            f'"outcome":"{outcome}","error":"{error}","units":{units}'
            "}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = _report(path)
    grouped = {(row["error"], row["kind"]): row for row in report["repeated_errors"]}
    timeout = grouped[("Timeout", "retry loop")]
    assert timeout["occurrences"] == 3
    assert timeout["longest_streak"] == 2
    assert timeout["units"] == "6"
    other = grouped[("other", "repeated")]
    assert other["occurrences"] == 2
    assert other["longest_streak"] == 1
    assert other["units"] == "8"
    assert all(row["error"] != "once" for row in report["repeated_errors"])


def test_even_gap_median_is_mean_of_central_gaps(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-10-01T00:00:00Z","routine":"r","trigger":"cron","outcome":"changed","units":1}',
                '{"timestamp":"2026-10-01T00:00:10Z","routine":"r","trigger":"cron","outcome":"changed","units":1}',
                '{"timestamp":"2026-10-01T00:00:40Z","routine":"r","trigger":"cron","outcome":"no-op","units":1}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = _report(path)
    row = report["schedules"][0]
    assert row["flagged"] is True
    assert row["fires"] == 3
    assert row["changes"] == 2
    assert row["fire_gaps_seconds"] == {"count": 2, "min": "10", "median": "20", "max": "30"}
    assert row["change_gaps_seconds"] == {"count": 1, "min": "10", "median": "10", "max": "10"}


def test_schedule_not_flagged_when_every_fire_changes(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        '{"timestamp":"2026-10-01T00:00:00Z","routine":"r","trigger":"timer","outcome":"CHANGED","units":3}\n',
        encoding="utf-8",
    )
    report = _report(path)
    assert report["schedules"][0]["flagged"] is False
    assert report["schedules"][0]["changes"] == 1
    assert "more often" in report["notes"]["schedule"]
    assert "wakegate" not in report["notes"]["schedule"]


def test_offset_timestamp_uses_utc_day(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        '{"timestamp":"2026-10-01T00:30:00+02:00","agent":"a","routine":"r","trigger":"manual","outcome":"changed","units":1}\n',
        encoding="utf-8",
    )
    report = _report(path)
    assert report["window"]["text"] == "2026-09-30T22:30:00Z .. 2026-09-30T22:30:00Z"
    assert report["spend"]["by_day"][0]["key"] == "2026-09-30"


def test_since_duration_anchors_to_the_log_not_the_clock():
    report = _report(since="1d")
    assert report["filter"]["since"] == "2026-10-01T12:00:00Z"
    assert report["filter"]["since_note"].startswith("duration 1d before the latest parsed timestamp")
    assert report["rows_used"] == 3
    assert report["rows_outside_window"] == 7
    assert report["units_total"] == "200"
    assert report["window"]["text"] == "2026-10-02T00:00:00Z .. 2026-10-02T12:00:00Z"
    assert report["file_span"]["text"] == "2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z"


def test_until_is_inclusive_and_inverted_range_errors():
    report = _report(until="2026-10-01T02:00:00Z")
    assert report["rows_used"] == 5
    assert report["units_total"] == "830"
    assert report["window"]["end"] == "2026-10-01T02:00:00Z"

    from usage_audit.errors import ConfigError
    import pytest

    with pytest.raises(ConfigError, match="later than"):
        _report(since="2026-10-02T00:00:00Z", until="2026-10-01T00:00:00Z")


def test_negative_units_stay_in_the_sum(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-10-01T00:00:00Z","routine":"r","trigger":"manual","outcome":"changed","units":2}',
                '{"timestamp":"2026-10-01T01:00:00Z","routine":"r","trigger":"manual","outcome":"changed","units":-5}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = _report(path)
    assert report["units_total"] == "-3"
    assert [row["units"] for row in report["top_runs"]] == ["2", "-5"]


def test_malformed_rows_are_omitted_and_naive_timestamps_are_utc(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        "\n".join(
            [
                "# synthetic example data",
                "",
                '{"timestamp":"2026-10-01T00:00:00","routine":"r","trigger":"manual","outcome":"NO-OP","units":"4"}',
                "{not json",
                "[]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = _report(path)
    assert report["rows_read"] == 3
    assert report["rows_used"] == 1
    assert report["malformed"] == 2
    assert report["units_total"] == "4"
    assert report["window"]["start"] == "2026-10-01T00:00:00Z"
    assert report["noop_by_routine"][0]["noop_runs"] == 1
    reasons = [item["reason"] for item in report["malformed_samples"]]
    assert reasons == ["invalid json", "row is not an object"]


def test_sniffed_log_and_custom_mapping(tmp_path):
    path = tmp_path / "agent.log"
    path.write_text(
        '{"ts":"2026-10-03T00:00:00Z","bot":"worker","trigger":"manual","routine":"task","tokens":8,"outcome":"changed"}\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "map.yaml"
    config_path.write_text(
        "mapping:\n  timestamp: ts\n  agent: bot\n  units: tokens\n",
        encoding="utf-8",
    )
    from usage_audit.config import load_config

    config = load_config(config_path)
    loaded = load_logs([str(path)], config)
    assert loaded.inputs[0]["format"] == "jsonl"
    report = build_report(loaded, config)
    assert report["units_total"] == "8"
    assert report["spend"]["by_agent"][0]["key"] == "worker"


def test_json_array_is_rejected(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text('[{"timestamp":"2026-10-01T00:00:00Z"}]\n', encoding="utf-8")
    from usage_audit.errors import LogError
    import pytest

    with pytest.raises(LogError, match="JSON arrays"):
        load_logs([str(path)], default_config())


def test_top_limit():
    report = _report(top=1)
    assert len(report["top_runs"]) == 1
    assert report["top_runs"][0]["units"] == "420"
    assert report["rows_with_recorded_units"] == 10
