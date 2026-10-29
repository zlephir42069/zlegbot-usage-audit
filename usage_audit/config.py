"""Load the field mapping. Built-in names are used when no file is present."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from usage_audit.errors import ConfigError

LOGICAL_FIELDS = (
    "timestamp",
    "agent",
    "trigger",
    "routine",
    "units",
    "outcome",
    "duration",
    "error",
)

DEFAULT_MAPPING = {name: name for name in LOGICAL_FIELDS}

_DEFAULT_OUTCOMES = {
    "noop": ("no-op", "noop", "unchanged"),
    "changed": ("changed",),
    "error": ("error", "failed", "failure"),
}
_DEFAULT_SCHEDULE = ("schedule", "cron", "timer")
_KNOWN_KEYS = {"mapping", "top", "retry_min", "outcomes", "triggers"}
_OUTCOME_CLASSES = ("noop", "changed", "error")


@dataclass(frozen=True)
class Config:
    mapping: dict[str, str]
    top: int
    retry_min: int
    outcome_labels: dict[str, tuple[str, ...]]
    outcome_sets: dict[str, frozenset[str]]
    schedule_labels: tuple[str, ...]
    schedule_triggers: frozenset[str]

    def classify_outcome(self, outcome: str) -> str:
        token = outcome.strip().casefold()
        if not token:
            return "other"
        for name in _OUTCOME_CLASSES:
            if token in self.outcome_sets[name]:
                return name
        return "other"

    def is_schedule(self, trigger: str) -> bool:
        return trigger.strip().casefold() in self.schedule_triggers


def default_config() -> Config:
    return _build(
        dict(DEFAULT_MAPPING),
        top=10,
        retry_min=2,
        outcomes={key: tuple(value) for key, value in _DEFAULT_OUTCOMES.items()},
        schedule=tuple(_DEFAULT_SCHEDULE),
    )


def load_config(path: Path) -> Config:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"could not read config: {exc.__class__.__name__}") from exc
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is a dependency
        raise ConfigError("PyYAML is required to read a config file") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc.__class__.__name__}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("config must be a mapping")
    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        raise ConfigError(f"unknown config key: {', '.join(unknown)}")

    mapping = dict(DEFAULT_MAPPING)
    if "mapping" in raw and raw["mapping"] is not None:
        incoming = raw["mapping"]
        if not isinstance(incoming, dict):
            raise ConfigError("mapping must be a mapping")
        for key, value in incoming.items():
            if key not in DEFAULT_MAPPING:
                raise ConfigError(f"unknown mapping field: {key}")
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"mapping.{key} must be a column name")
            mapping[key] = value.strip()

    top = _positive_int(raw.get("top", 10), "top")
    retry_min = _positive_int(raw.get("retry_min", 2), "retry_min")
    if retry_min < 2:
        raise ConfigError("retry_min must be at least 2")

    outcomes = {key: tuple(value) for key, value in _DEFAULT_OUTCOMES.items()}
    if "outcomes" in raw and raw["outcomes"] is not None:
        outcomes = _parse_outcomes(raw["outcomes"])

    schedule = tuple(_DEFAULT_SCHEDULE)
    if "triggers" in raw and raw["triggers"] is not None:
        schedule = _parse_schedule(raw["triggers"])

    return _build(mapping, top=top, retry_min=retry_min, outcomes=outcomes, schedule=schedule)


def _build(mapping, *, top, retry_min, outcomes, schedule) -> Config:
    outcome_sets = {}
    seen: dict[str, str] = {}
    labels: dict[str, tuple[str, ...]] = {}
    for name in _OUTCOME_CLASSES:
        cleaned = []
        folded = []
        for item in outcomes[name]:
            token = item.strip()
            fold = token.casefold()
            if not fold:
                raise ConfigError(f"outcomes.{name} contains an empty label")
            if fold in seen:
                raise ConfigError(
                    f"outcome label {token!r} is listed under {seen[fold]} and {name}"
                )
            seen[fold] = name
            cleaned.append(token)
            folded.append(fold)
        labels[name] = tuple(cleaned)
        outcome_sets[name] = frozenset(folded)
    schedule_labels = []
    schedule_folds = []
    seen_trigger: set[str] = set()
    for item in schedule:
        token = item.strip()
        fold = token.casefold()
        if not fold:
            raise ConfigError("triggers.schedule contains an empty label")
        if fold in seen_trigger:
            raise ConfigError(f"duplicate schedule trigger {token!r}")
        seen_trigger.add(fold)
        schedule_labels.append(token)
        schedule_folds.append(fold)
    return Config(
        mapping=mapping,
        top=top,
        retry_min=retry_min,
        outcome_labels=labels,
        outcome_sets=outcome_sets,
        schedule_labels=tuple(schedule_labels),
        schedule_triggers=frozenset(schedule_folds),
    )


def _parse_outcomes(raw) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, dict):
        raise ConfigError("outcomes must be a mapping")
    unknown = sorted(set(raw) - set(_OUTCOME_CLASSES))
    if unknown:
        raise ConfigError(f"unknown outcome class: {', '.join(unknown)}")
    parsed = {}
    for name in _OUTCOME_CLASSES:
        if name not in raw:
            raise ConfigError(f"outcomes.{name} is required when outcomes is set")
        parsed[name] = tuple(_label_list(raw[name], f"outcomes.{name}"))
    return parsed


def _parse_schedule(raw) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        raise ConfigError("triggers must be a mapping")
    unknown = sorted(set(raw) - {"schedule"})
    if unknown:
        raise ConfigError(f"unknown trigger class: {', '.join(unknown)}")
    if "schedule" not in raw:
        raise ConfigError("triggers.schedule is required when triggers is set")
    return tuple(_label_list(raw["schedule"], "triggers.schedule"))


def _label_list(raw, where: str) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(f"{where} must be a non-empty list")
    labels = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{where} entries must be strings")
        labels.append(item.strip())
    return labels


def _positive_int(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{where} must be a positive integer")
    return value
