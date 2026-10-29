"""CLI exit codes. 0 ok, 1 a log problem, 2 a config or usage error."""

import json
import shutil
import site
import subprocess
import sys
import sysconfig
from pathlib import Path

from conftest import EXAMPLE_CONFIG, REPO, SAMPLE_CSV, SAMPLE_JSONL


def _run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "usage_audit", *args],
        cwd=cwd or REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_schema_prints_mapping_example():
    result = _run("schema")
    assert result.returncode == 0, result.stderr
    assert "mapping:" in result.stdout
    assert "timestamp" in result.stdout
    assert "units: tokens" in result.stdout
    assert result.stderr == ""


def test_validate_and_report_sample():
    checked = _run("validate", str(SAMPLE_JSONL))
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout.splitlines()[0] == "ok"
    assert "rows: 10" in checked.stdout
    assert "file span: 2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z" in checked.stdout

    csv_checked = _run("validate", str(SAMPLE_CSV), "--config", str(EXAMPLE_CONFIG))
    assert csv_checked.returncode == 0, csv_checked.stderr
    assert "rows: 10" in csv_checked.stdout

    report = _run("report", str(SAMPLE_JSONL))
    assert report.returncode == 0, report.stderr
    assert "units total: 1850" in report.stdout
    assert "input window: 2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z" in report.stdout

    as_json = _run("report", str(SAMPLE_JSONL), "--json", "--top", "1")
    assert as_json.returncode == 0, as_json.stderr
    payload = json.loads(as_json.stdout)
    assert payload["units_total"] == "1850"
    assert len(payload["top_runs"]) == 1
    assert payload["top_runs"][0]["units"] == "420"


def test_validate_rejects_bad_rows_and_report_counts_them(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-10-01T00:00:00Z","units":1,"outcome":"changed","routine":"r","trigger":"manual"}',
                "{nope",
                '{"timestamp":"2026-10-01T01:00:00Z","units":true,"outcome":"changed","routine":"r","trigger":"manual"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    checked = _run("validate", str(path))
    assert checked.returncode == 1
    assert "invalid json" in checked.stderr
    assert "units is not a finite number" in checked.stderr
    assert "ok" not in checked.stdout

    report = _run("report", str(path))
    assert report.returncode == 0, report.stderr
    assert "units total: 1" in report.stdout
    assert "malformed rows: 1" in report.stdout
    assert "rows with unreadable units: 1" in report.stdout


def test_missing_log_and_bad_config(tmp_path):
    missing = _run("report", str(tmp_path / "nope.jsonl"))
    assert missing.returncode == 1
    assert "log not found" in missing.stderr

    bad = _run("validate", str(SAMPLE_JSONL), "--config", str(tmp_path / "missing.yaml"))
    assert bad.returncode == 2
    assert "config not found" in bad.stderr

    usage = _run("report")
    assert usage.returncode == 2

    bad_since = _run("report", str(SAMPLE_JSONL), "--since", "tomorrow")
    assert bad_since.returncode == 2
    assert "config error:" in bad_since.stderr

    bad_top = _run("report", str(SAMPLE_JSONL), "--top", "0")
    assert bad_top.returncode == 2


def test_auto_config_and_empty_log(tmp_path):
    log = tmp_path / "runs.jsonl"
    log.write_text(
        '{"ts":"2026-10-01T00:00:00Z","routine":"r","trigger":"manual","outcome":"changed","tokens":6}\n',
        encoding="utf-8",
    )
    (tmp_path / "usage-audit.yaml").write_text(
        "mapping:\n  timestamp: ts\n  units: tokens\n",
        encoding="utf-8",
    )
    report = _run("report", "runs.jsonl", cwd=tmp_path)
    assert report.returncode == 0, report.stderr
    assert "units total: 6" in report.stdout

    empty = tmp_path / "empty.jsonl"
    empty.write_text("# synthetic example data\n\n", encoding="utf-8")
    checked = _run("validate", str(empty))
    assert checked.returncode == 1
    assert "no records" in checked.stderr
    printed = _run("report", str(empty))
    assert printed.returncode == 0, printed.stderr
    assert "input window: empty" in printed.stdout
    assert "units total: 0" in printed.stdout


def _console_script():
    candidates = [
        Path(sysconfig.get_path("scripts")) / "usage-audit",
        Path(site.getuserbase()) / "bin" / "usage-audit",
    ]
    found = shutil.which("usage-audit")
    if found:
        candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def test_console_script_schema():
    script = _console_script()
    assert script.is_file(), script
    result = subprocess.run(
        [str(script), "schema"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Logical fields" in result.stdout
