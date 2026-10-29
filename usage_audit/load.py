"""Read JSONL or CSV logs into records. One record is one run or turn."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from usage_audit.config import Config
from usage_audit.duration import parse_timestamp
from usage_audit.errors import LogError
from usage_audit.units import UnitsError, format_units, is_plain_number, parse_units

_JSONL_SUFFIXES = {".jsonl", ".ndjson", ".json"}
_SAMPLE_LIMIT = 20


@dataclass
class Record:
    timestamp: datetime
    agent: str
    trigger: str
    routine: str
    units: Decimal | None
    units_state: str
    outcome: str
    outcome_class: str
    duration: str
    error: str
    source: str
    line: int
    seq: int

    @property
    def agent_key(self) -> str:
        return self.agent.casefold()

    @property
    def trigger_key(self) -> str:
        return self.trigger.casefold()

    @property
    def routine_key(self) -> str:
        return self.routine.casefold()

    @property
    def error_key(self) -> str:
        return self.error.casefold()


@dataclass
class Malformed:
    source: str
    line: int
    reason: str


@dataclass
class LoadResult:
    records: list[Record] = field(default_factory=list)
    malformed: list[Malformed] = field(default_factory=list)
    inputs: list[dict[str, str]] = field(default_factory=list)

    @property
    def rows_read(self) -> int:
        return len(self.records) + len(self.malformed)


def load_logs(paths: list[str], config: Config) -> LoadResult:
    if not paths:
        raise LogError("no log files given")
    missing = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            missing.append(f"log not found: {raw}")
        elif not path.is_file():
            missing.append(f"log is not a file: {raw}")
    if missing:
        raise LogError(missing)

    result = LoadResult()
    seq = 0
    for raw in paths:
        path = Path(raw)
        data_lines = _read_data_lines(path, raw)
        kind = _detect_format(path, data_lines)
        result.inputs.append({"path": raw, "format": kind})
        if kind == "csv":
            rows = _csv_rows(data_lines)
        else:
            rows = _jsonl_rows(data_lines)
        for line_no, payload, problem in rows:
            if problem is not None:
                result.malformed.append(Malformed(raw, line_no, problem))
                continue
            record, problem = _record_from_mapping(payload, config, raw, line_no, seq)
            if problem is not None:
                result.malformed.append(Malformed(raw, line_no, problem))
                continue
            result.records.append(record)
            seq += 1
    return result


def _read_data_lines(path: Path, label: str) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LogError(f"{label}: not valid utf-8") from exc
    except OSError as exc:
        raise LogError(f"{label}: could not read log: {exc.__class__.__name__}") from exc
    data_lines = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        data_lines.append((line_no, line))
    return data_lines


def _detect_format(path: Path, data_lines: list[tuple[int, str]]) -> str:
    suffix = path.suffix.lower()
    if suffix in _JSONL_SUFFIXES:
        kind = "jsonl"
    elif suffix == ".csv":
        kind = "csv"
    elif not data_lines:
        kind = "jsonl"
    elif data_lines[0][1].lstrip().startswith("{"):
        kind = "jsonl"
    else:
        kind = "csv"
    if kind == "jsonl" and data_lines and data_lines[0][1].lstrip().startswith("["):
        raise LogError(
            f"{path}: JSON arrays are not accepted; use one JSON object per line"
        )
    return kind


def _jsonl_rows(data_lines: list[tuple[int, str]]):
    for line_no, line in data_lines:
        try:
            payload = json.loads(line, parse_float=Decimal, parse_int=Decimal)
        except json.JSONDecodeError:
            yield line_no, None, "invalid json"
            continue
        if not isinstance(payload, dict):
            yield line_no, None, "row is not an object"
            continue
        yield line_no, payload, None


def _csv_rows(data_lines: list[tuple[int, str]]):
    if not data_lines:
        return
    line_nos = [line_no for line_no, _line in data_lines]
    lines = [line for _line_no, line in data_lines]
    try:
        reader = csv.DictReader(lines)
    except csv.Error:
        yield line_nos[0], None, "invalid csv"
        return
    if not reader.fieldnames or any(name is None or not str(name).strip() for name in reader.fieldnames):
        yield line_nos[0], None, "csv header is missing a column name"
        return
    for line_no, row in zip(line_nos[1:], reader):
        if row is None:
            yield line_no, None, "invalid csv"
            continue
        if None in row:
            yield line_no, None, "csv row has more columns than the header"
            continue
        yield line_no, {key: value for key, value in row.items()}, None


def _record_from_mapping(payload: dict, config: Config, source: str, line: int, seq: int):
    timestamp_raw = _lookup(payload, config.mapping["timestamp"])
    if timestamp_raw is None or (isinstance(timestamp_raw, str) and not timestamp_raw.strip()):
        return None, "missing timestamp"
    if not isinstance(timestamp_raw, str):
        return None, "timestamp must be a string"
    try:
        timestamp = parse_timestamp(timestamp_raw)
    except ValueError:
        return None, "invalid timestamp"

    agent = _label(payload, config.mapping["agent"])
    trigger = _label(payload, config.mapping["trigger"])
    routine = _label(payload, config.mapping["routine"])
    outcome = _label(payload, config.mapping["outcome"])
    error = _label(payload, config.mapping["error"])
    duration = _duration(payload, config.mapping["duration"])

    units, units_state, units_problem = _units(payload, config.mapping["units"])
    if units_problem is not None:
        return None, units_problem

    return (
        Record(
            timestamp=timestamp,
            agent=agent,
            trigger=trigger,
            routine=routine,
            units=units,
            units_state=units_state,
            outcome=outcome,
            outcome_class=config.classify_outcome(outcome),
            duration=duration,
            error=error,
            source=source,
            line=line,
            seq=seq,
        ),
        None,
    )


def _lookup(payload: dict, key: str):
    if key not in payload:
        return None
    return payload[key]


def _label(payload: dict, key: str) -> str:
    value = _lookup(payload, key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return ""
    if isinstance(value, Decimal):
        return format_units(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _duration(payload: dict, key: str) -> str:
    value = _lookup(payload, key)
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if is_plain_number(text):
            try:
                return format_units(parse_units(text))
            except UnitsError:
                return text
        return text
    if isinstance(value, Decimal):
        return format_units(value)
    if isinstance(value, (int, float)):
        try:
            parsed = parse_units(value)
        except UnitsError:
            return ""
        if parsed is None:
            return ""
        return format_units(parsed)
    return ""


def _units(payload: dict, key: str):
    if key not in payload:
        return None, "missing", None
    value = payload[key]
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "missing", None
    try:
        parsed = parse_units(value)
    except UnitsError:
        return None, "unreadable", None
    if parsed is None:
        return None, "missing", None
    return parsed, "recorded", None


def sample_malformed(items: list[Malformed], limit: int = _SAMPLE_LIMIT) -> tuple[list[dict], int]:
    ordered = sorted(items, key=lambda item: (item.source, item.line))
    shown = [
        {"source": item.source, "line": item.line, "reason": item.reason}
        for item in ordered[:limit]
    ]
    return shown, max(0, len(ordered) - len(shown))
