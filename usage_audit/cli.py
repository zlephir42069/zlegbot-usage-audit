"""Command line: report, validate, schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from usage_audit.duration import format_timestamp
from usage_audit.errors import ConfigError, LogError
from usage_audit.schema_text import SCHEMA_TEXT


def main(argv=None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code is None else int(code)

    try:
        if args.command == "schema":
            print(SCHEMA_TEXT, end="", flush=True)
            return 0
        if args.command == "validate":
            return _validate(args)
        if args.command == "report":
            return _report(args)
    except ConfigError as exc:
        for message in exc.messages:
            print(f"config error: {message}", file=sys.stderr, flush=True)
        return 2
    except LogError as exc:
        for message in exc.messages:
            print(f"log error: {message}", file=sys.stderr, flush=True)
        return 1
    except BrokenPipeError:
        return 0
    print("config error: unknown command", file=sys.stderr, flush=True)
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usage-audit",
        description=(
            "Total recorded agent spend and flag no-op wakes, chatty schedules, and repeated errors."
        ),
        epilog=(
            "Exit codes: 0 ok, 1 log missing, unreadable, or rejected by validate, "
            "2 usage or config error."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="summarize one or more logs")
    _add_logs(report)
    _add_config(report)
    report.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    report.add_argument(
        "--top",
        type=int,
        help="costliest runs to list (default: 10, or top from the config)",
    )
    report.add_argument(
        "--since",
        help="ISO timestamp, or a duration before the latest timestamp in the log",
    )
    report.add_argument("--until", help="inclusive ISO timestamp")

    validate = sub.add_parser("validate", help="check that logs parse and timestamps are usable")
    _add_logs(validate)
    _add_config(validate)

    sub.add_parser("schema", help="print the expected fields and a mapping example")
    return parser


def _add_logs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("logs", nargs="+", help="JSONL or CSV log files")


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        help="field mapping YAML (default: usage-audit.yaml in the current directory if it exists)",
    )


def _validate(args) -> int:
    from usage_audit.config import load_config
    from usage_audit.load import load_logs

    config = _config_from_args(args, load_config)
    result = load_logs(list(args.logs), config)
    messages = []
    malformed = sorted(result.malformed, key=lambda item: (item.source, item.line))
    for item in malformed:
        messages.append(f"{item.source}:{item.line}: {item.reason}")
    for rec in result.records:
        if rec.units_state == "unreadable":
            messages.append(f"{rec.source}:{rec.line}: units is not a finite number")
    if not result.records and not result.malformed:
        messages.append("no records")
    if messages:
        shown = messages[:50]
        for message in shown:
            print(f"log error: {message}", file=sys.stderr, flush=True)
        extra = len(messages) - len(shown)
        if extra:
            print(f"log error: {extra} more", file=sys.stderr, flush=True)
        return 1
    print("ok", flush=True)
    print(f"rows: {len(result.records)}", flush=True)
    print("malformed: 0", flush=True)
    print(f"file span: {_span_text(result.records)}", flush=True)
    return 0


def _report(args) -> int:
    from usage_audit.analyze import build_report
    from usage_audit.config import load_config
    from usage_audit.load import load_logs
    from usage_audit.report import render_json, render_markdown

    config = _config_from_args(args, load_config)
    loaded = load_logs(list(args.logs), config)
    report = build_report(loaded, config, since=args.since, until=args.until, top=args.top)
    if args.json:
        print(render_json(report), end="", flush=True)
    else:
        print(render_markdown(report), end="", flush=True)
    return 0


def _config_from_args(args, load_config):
    from usage_audit.config import default_config

    chosen = args.config
    if chosen:
        path = Path(chosen)
        if not path.is_file():
            raise ConfigError(f"config not found: {path}")
        return load_config(path)
    default_path = Path("usage-audit.yaml")
    if default_path.is_file():
        return load_config(default_path)
    return default_config()


def _span_text(records) -> str:
    if not records:
        return "empty"
    start = min(rec.timestamp for rec in records)
    end = max(rec.timestamp for rec in records)
    return f"{format_timestamp(start)} .. {format_timestamp(end)}"
