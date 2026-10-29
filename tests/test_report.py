"""Markdown and JSON render the same computed report."""

import json

from usage_audit.analyze import build_report
from usage_audit.config import default_config
from usage_audit.load import load_logs
from usage_audit.report import render_json, render_markdown

from conftest import SAMPLE_JSONL


def _rendered():
    loaded = load_logs([str(SAMPLE_JSONL)], default_config())
    report = build_report(loaded, default_config())
    return report, render_markdown(report), render_json(report)


def test_markdown_states_the_window_and_sample_sums():
    _report, markdown, _raw = _rendered()
    assert markdown.startswith("# usage-audit report\n")
    assert "input window: 2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z" in markdown
    assert "file span: 2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z" in markdown
    assert "units total: 1850" in markdown
    assert "runs total: 10" in markdown
    assert "| poll-inbox | 6 | 3 | 3/6 | 300 |" in markdown
    assert "| daily-digest | 4 | 1 | 1/4 | 10 |" in markdown
    assert "poll-inbox: fire gaps: n=3 min 900 median 900 max 84600 seconds." in markdown
    assert "daily-digest: fire gaps: n=3 min 300 median 300 max 121800 seconds." in markdown
    assert "https://github.com/zlephir42069/zlegbot-wakegate" in markdown
    assert "recommended cron expression" in markdown
    assert "*/" not in markdown
    assert "upstream timeout" in markdown
    assert "retry loop" in markdown
    assert "Showing 10 of 10 rows that recorded units." in markdown
    assert "| 420 | 2026-10-01T02:10:00Z | digest-bot | daily-digest |" in markdown
    assert "estimat" not in markdown.lower()
    assert "$" not in markdown


def test_json_matches_the_report_object():
    report, _markdown, raw = _rendered()
    parsed = json.loads(raw)
    assert parsed == report
    assert raw.endswith("\n")


def test_empty_sections_and_pipe_escaping(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        '{"timestamp":"2026-10-01T00:00:00Z","agent":"a|b","routine":"r","trigger":"manual","outcome":"changed","units":1,"error":"x|y"}\n',
        encoding="utf-8",
    )
    loaded = load_logs([str(path)], default_config())
    report = build_report(loaded, default_config())
    markdown = render_markdown(report)
    assert "(none)" in markdown
    assert "No schedule-triggered rows" in markdown
    assert r"a\|b" in markdown
    section = markdown.split("## Repeated identical errors", 1)[1].split("## ", 1)[0]
    assert "| retry loop |" not in section
