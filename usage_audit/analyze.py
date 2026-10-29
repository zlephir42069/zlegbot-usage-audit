"""Counts and sums over an input window. Nothing here invents a unit value."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from usage_audit import __version__
from usage_audit.config import Config
from usage_audit.duration import format_timestamp, parse_duration, parse_timestamp
from usage_audit.errors import ConfigError
from usage_audit.load import LoadResult, Record, sample_malformed
from usage_audit.units import add_units, format_units

UNITS_NOTE = (
    "Unit totals are sums of the units field on rows in the input window that recorded "
    "a finite number. Rows that omit units are counted in run totals and are not given "
    "a filled-in value. Unreadable units are counted separately and are not treated as zero."
)
TIMEZONE_NOTE = "Timestamps without an offset are read as UTC. Day buckets use the UTC date."
WINDOW_NOTE = (
    "The input window is the earliest and latest timestamp among rows included in the totals."
)
MALFORMED_NOTE = (
    "Malformed rows are omitted from every total. Blank lines and lines that start with # are not rows."
)
SCHEDULE_RULE = (
    "A schedule row is flagged when its fires are greater than its runs whose outcome class "
    "is changed. Gaps are seconds between consecutive rows of that routine, keeping input "
    "order when timestamps tie. The median of an even count is the mean of the two central gaps."
)
SUGGESTION = (
    "Schedule fires exceed recorded changes for at least one routine. "
    "The log does not contain a recommended cron expression. "
    "A slower cadence, or a cron-first wake gate such as zlegbot-wakegate "
    "(https://github.com/zlephir42069/zlegbot-wakegate), starts the agent only after a cheap check fires."
)
NONE_FLAGGED = "No schedule in this window fired more often than it recorded a change."
NO_SCHEDULE = "No schedule-triggered rows in this window."
RETRY_NOTE = (
    "A retry loop is a consecutive run of the same error text for the same agent and routine. "
    "A different outcome, or a different error text, breaks the run. Occurrences count every "
    "matching row in the window. Units are the sum of recorded units on those rows."
)


@dataclass
class _Bucket:
    key: str
    runs: int = 0
    units: list[Decimal] = field(default_factory=list)
    missing: int = 0
    unreadable: int = 0


@dataclass
class _Noop:
    routine: str
    runs: int = 0
    noop_runs: int = 0
    units: list[Decimal] = field(default_factory=list)
    missing: int = 0
    unreadable: int = 0


@dataclass
class _Schedule:
    routine: str
    agents: list[str] = field(default_factory=list)
    agent_seen: set[str] = field(default_factory=set)
    fires: int = 0
    changes: int = 0
    noops: int = 0
    errors: int = 0
    other: int = 0
    units: list[Decimal] = field(default_factory=list)
    missing: int = 0
    unreadable: int = 0
    stamps: list[datetime] = field(default_factory=list)
    change_stamps: list[datetime] = field(default_factory=list)


@dataclass
class _ErrorGroup:
    agent: str
    routine: str
    error: str
    occurrences: int = 0
    longest_streak: int = 0
    units: list[Decimal] = field(default_factory=list)
    missing: int = 0
    unreadable: int = 0
    first: datetime | None = None
    last: datetime | None = None


def build_report(
    loaded: LoadResult,
    config: Config,
    *,
    since: str | None = None,
    until: str | None = None,
    top: int | None = None,
) -> dict:
    top_n = config.top if top is None else top
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ConfigError("--top must be a positive integer")

    included, window_meta = _apply_window(loaded.records, since, until)
    samples, omitted = sample_malformed(loaded.malformed)
    recorded = [rec.units for rec in included if rec.units_state == "recorded" and rec.units is not None]
    missing = sum(1 for rec in included if rec.units_state == "missing")
    unreadable = sum(1 for rec in included if rec.units_state == "unreadable")
    ranked = [rec for rec in included if rec.units_state == "recorded" and rec.units is not None]
    ranked.sort(key=lambda rec: (rec.units, rec.timestamp, rec.seq), reverse=True)

    schedules = _schedules(included, config)
    suggestion = _schedule_note(schedules)
    return {
        "version": __version__,
        "inputs": list(loaded.inputs),
        "rows_read": loaded.rows_read,
        "rows_used": len(included),
        "rows_outside_window": window_meta["outside"],
        "malformed": len(loaded.malformed),
        "malformed_samples": samples,
        "malformed_omitted": omitted,
        "rows_missing_units": missing,
        "rows_unreadable_units": unreadable,
        "rows_with_recorded_units": len(ranked),
        "file_span": window_meta["file_span"],
        "window": window_meta["window"],
        "filter": window_meta["filter"],
        "runs_total": len(included),
        "units_total": format_units(add_units(recorded)),
        "spend": {
            "by_agent": _spend(included, lambda rec: rec.agent_key, lambda rec: rec.agent),
            "by_routine": _spend(included, lambda rec: rec.routine_key, lambda rec: rec.routine),
            "by_trigger": _spend(included, lambda rec: rec.trigger_key, lambda rec: rec.trigger),
            "by_day": _spend_by_day(included),
        },
        "noop_by_routine": _noop(included),
        "schedules": schedules,
        "repeated_errors": _repeated(included, config.retry_min),
        "top_runs": [_top_row(rec) for rec in ranked[:top_n]],
        "top": top_n,
        "retry_min": config.retry_min,
        "classification": {
            "noop": list(config.outcome_labels["noop"]),
            "changed": list(config.outcome_labels["changed"]),
            "error": list(config.outcome_labels["error"]),
            "schedule_triggers": list(config.schedule_labels),
        },
        "notes": {
            "units": UNITS_NOTE,
            "timezone": TIMEZONE_NOTE,
            "window": WINDOW_NOTE,
            "malformed": MALFORMED_NOTE,
            "schedule_rule": SCHEDULE_RULE,
            "schedule": suggestion,
            "retry": RETRY_NOTE,
        },
    }


def _apply_window(records: list[Record], since: str | None, until: str | None) -> tuple[list[Record], dict]:
    file_start = min((rec.timestamp for rec in records), default=None)
    file_end = max((rec.timestamp for rec in records), default=None)
    since_bound, since_note = _resolve_since(since, records)
    until_bound = _resolve_until(until)
    if since_bound is not None and until_bound is not None and since_bound > until_bound:
        raise ConfigError("--since is later than --until")

    included = []
    for rec in records:
        if since_bound is not None and rec.timestamp < since_bound:
            continue
        if until_bound is not None and rec.timestamp > until_bound:
            continue
        included.append(rec)
    start = min((rec.timestamp for rec in included), default=None)
    end = max((rec.timestamp for rec in included), default=None)
    return included, {
        "outside": len(records) - len(included),
        "file_span": _span(file_start, file_end, len(records)),
        "window": _span(start, end, len(included)),
        "filter": {
            "since": format_timestamp(since_bound) if since_bound is not None else None,
            "until": format_timestamp(until_bound) if until_bound is not None else None,
            "since_note": since_note,
        },
    }


def _span(start: datetime | None, end: datetime | None, rows: int) -> dict:
    if start is None or end is None:
        return {"start": None, "end": None, "text": "empty", "rows": rows}
    start_text = format_timestamp(start)
    end_text = format_timestamp(end)
    return {
        "start": start_text,
        "end": end_text,
        "text": f"{start_text} .. {end_text}",
        "rows": rows,
    }


def _resolve_since(since: str | None, records: list[Record]) -> tuple[datetime | None, str]:
    if since is None or not str(since).strip():
        return None, ""
    text = str(since).strip()
    try:
        duration = parse_duration(text)
    except ValueError:
        duration = None
    if duration is not None:
        if not records:
            raise ConfigError(
                "no timestamps in the input, so a duration --since cannot be resolved"
            )
        anchor = max(rec.timestamp for rec in records)
        bound = anchor - duration
        note = (
            f"duration {text} before the latest parsed timestamp {format_timestamp(anchor)}"
        )
        return bound, note
    try:
        return parse_timestamp(text), "absolute timestamp"
    except ValueError as exc:
        raise ConfigError(
            f"invalid --since {since!r} (use a duration like 7d or an ISO timestamp)"
        ) from exc


def _resolve_until(until: str | None) -> datetime | None:
    if until is None or not str(until).strip():
        return None
    try:
        return parse_timestamp(str(until).strip())
    except ValueError as exc:
        raise ConfigError(f"invalid --until {until!r} (use an ISO timestamp)") from exc


def _add(bucket: _Bucket, rec: Record) -> None:
    bucket.runs += 1
    _tally(bucket, rec)


def _tally(bucket, rec: Record) -> None:
    if rec.units_state == "recorded" and rec.units is not None:
        bucket.units.append(rec.units)
    elif rec.units_state == "unreadable":
        bucket.unreadable += 1
    else:
        bucket.missing += 1


def _bucket_dict(bucket: _Bucket) -> dict:
    return {
        "key": bucket.key,
        "runs": bucket.runs,
        "units": format_units(add_units(bucket.units)),
        "missing_units": bucket.missing,
        "unreadable_units": bucket.unreadable,
    }


def _spend(records: list[Record], key_fn, label_fn) -> list[dict]:
    buckets: dict[str, _Bucket] = {}
    for rec in records:
        key = key_fn(rec)
        label = label_fn(rec).strip() or "(none)"
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _Bucket(label)
            buckets[key] = bucket
        _add(bucket, rec)
    ordered = sorted(
        buckets.values(),
        key=lambda bucket: (-add_units(bucket.units), -bucket.runs, bucket.key.casefold()),
    )
    return [_bucket_dict(bucket) for bucket in ordered]


def _spend_by_day(records: list[Record]) -> list[dict]:
    buckets: dict[str, _Bucket] = {}
    for rec in records:
        key = rec.timestamp.date().isoformat()
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _Bucket(key)
            buckets[key] = bucket
        _add(bucket, rec)
    ordered = sorted(buckets.values(), key=lambda bucket: bucket.key)
    return [_bucket_dict(bucket) for bucket in ordered]


def _noop(records: list[Record]) -> list[dict]:
    groups: dict[str, _Noop] = {}
    for rec in records:
        label = rec.routine.strip() or "(none)"
        group = groups.get(rec.routine_key)
        if group is None:
            group = _Noop(label)
            groups[rec.routine_key] = group
        group.runs += 1
        if rec.outcome_class != "noop":
            continue
        group.noop_runs += 1
        if rec.units_state == "recorded" and rec.units is not None:
            group.units.append(rec.units)
        elif rec.units_state == "unreadable":
            group.unreadable += 1
        else:
            group.missing += 1
    ordered = sorted(
        groups.values(),
        key=lambda group: (-add_units(group.units), -group.noop_runs, group.routine.casefold()),
    )
    return [
        {
            "routine": group.routine,
            "runs": group.runs,
            "noop_runs": group.noop_runs,
            "noop_units": format_units(add_units(group.units)),
            "noop_missing_units": group.missing,
            "noop_unreadable_units": group.unreadable,
        }
        for group in ordered
    ]


def _schedules(records: list[Record], config: Config) -> list[dict]:
    groups: dict[str, _Schedule] = {}
    for rec in sorted(records, key=lambda item: (item.timestamp, item.seq)):
        if not config.is_schedule(rec.trigger):
            continue
        label = rec.routine.strip() or "(none)"
        group = groups.get(rec.routine_key)
        if group is None:
            group = _Schedule(label)
            groups[rec.routine_key] = group
        _remember(group.agents, group.agent_seen, rec.agent)
        group.fires += 1
        if rec.outcome_class == "changed":
            group.changes += 1
            group.change_stamps.append(rec.timestamp)
        elif rec.outcome_class == "noop":
            group.noops += 1
        elif rec.outcome_class == "error":
            group.errors += 1
        else:
            group.other += 1
        if rec.units_state == "recorded" and rec.units is not None:
            group.units.append(rec.units)
        elif rec.units_state == "unreadable":
            group.unreadable += 1
        else:
            group.missing += 1
        group.stamps.append(rec.timestamp)
    rendered = []
    for group in groups.values():
        rendered.append(
            {
                "routine": group.routine,
                "agents": list(group.agents),
                "fires": group.fires,
                "changes": group.changes,
                "noops": group.noops,
                "errors": group.errors,
                "other": group.other,
                "units": format_units(add_units(group.units)),
                "missing_units": group.missing,
                "unreadable_units": group.unreadable,
                "flagged": group.fires > group.changes,
                "fire_gaps_seconds": _gaps(group.stamps),
                "change_gaps_seconds": _gaps(group.change_stamps),
            }
        )
    rendered.sort(key=lambda row: (not row["flagged"], -row["fires"], row["routine"].casefold()))
    return rendered


def _schedule_note(schedules: list[dict]) -> str:
    if not schedules:
        return NO_SCHEDULE
    if any(row["flagged"] for row in schedules):
        return SUGGESTION
    return NONE_FLAGGED


def _gaps(stamps: list[datetime]) -> dict | None:
    if len(stamps) < 2:
        return None
    gaps = [_gap_seconds(earlier, later) for earlier, later in zip(stamps, stamps[1:])]
    ordered = sorted(gaps)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        median = ordered[mid]
    else:
        median = (ordered[mid - 1] + ordered[mid]) / Decimal(2)
    return {
        "count": count,
        "min": format_units(ordered[0]),
        "median": format_units(median),
        "max": format_units(ordered[-1]),
    }


def _gap_seconds(earlier: datetime, later: datetime) -> Decimal:
    delta = later - earlier
    seconds = delta.days * 86400 + delta.seconds
    return Decimal(seconds) + (Decimal(delta.microseconds) / Decimal(1_000_000))


def _repeated(records: list[Record], retry_min: int) -> list[dict]:
    by_pair: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for rec in sorted(records, key=lambda item: (item.timestamp, item.seq)):
        by_pair[(rec.agent_key, rec.routine_key)].append(rec)

    groups: dict[tuple[str, str, str], _ErrorGroup] = {}
    for rows in by_pair.values():
        streak_key = None
        streak = 0
        for rec in rows:
            if rec.outcome_class != "error":
                streak_key = None
                streak = 0
                continue
            key = (rec.agent_key, rec.routine_key, rec.error_key)
            group = groups.get(key)
            if group is None:
                group = _ErrorGroup(
                    agent=rec.agent.strip() or "(none)",
                    routine=rec.routine.strip() or "(none)",
                    error=rec.error.strip(),
                )
                groups[key] = group
            group.occurrences += 1
            if rec.units_state == "recorded" and rec.units is not None:
                group.units.append(rec.units)
            elif rec.units_state == "unreadable":
                group.unreadable += 1
            else:
                group.missing += 1
            if group.first is None or rec.timestamp < group.first:
                group.first = rec.timestamp
            if group.last is None or rec.timestamp > group.last:
                group.last = rec.timestamp
            if streak_key == rec.error_key:
                streak += 1
            else:
                streak_key = rec.error_key
                streak = 1
            if streak > group.longest_streak:
                group.longest_streak = streak

    rendered = []
    for group in groups.values():
        if group.occurrences < retry_min:
            continue
        kind = "retry loop" if group.longest_streak >= retry_min else "repeated"
        rendered.append(
            {
                "agent": group.agent,
                "routine": group.routine,
                "error": group.error,
                "kind": kind,
                "occurrences": group.occurrences,
                "longest_streak": group.longest_streak,
                "units": format_units(add_units(group.units)),
                "missing_units": group.missing,
                "unreadable_units": group.unreadable,
                "first": format_timestamp(group.first) if group.first is not None else None,
                "last": format_timestamp(group.last) if group.last is not None else None,
            }
        )
    rendered.sort(
        key=lambda row: (
            -row["occurrences"],
            -Decimal(row["units"]),
            row["agent"].casefold(),
            row["routine"].casefold(),
            row["error"].casefold(),
        )
    )
    return rendered


def _remember(names: list[str], seen: set[str], label: str) -> None:
    shown = label.strip() or "(none)"
    fold = shown.casefold()
    if fold in seen:
        return
    seen.add(fold)
    names.append(shown)


def _top_row(rec: Record) -> dict:
    units = rec.units if rec.units is not None else Decimal(0)
    return {
        "units": format_units(units),
        "timestamp": format_timestamp(rec.timestamp),
        "agent": rec.agent or "(none)",
        "routine": rec.routine or "(none)",
        "trigger": rec.trigger or "(none)",
        "outcome": rec.outcome or "(none)",
        "outcome_class": rec.outcome_class,
        "duration": rec.duration,
        "error": rec.error,
        "source": rec.source,
        "line": rec.line,
    }
