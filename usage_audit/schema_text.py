"""Text printed by `usage-audit schema`."""

from usage_audit import __version__

SCHEMA_TEXT = f"""usage-audit {__version__}

One agent run or turn per record. JSONL is one JSON object per line
(.jsonl, .ndjson). CSV has a header row. Blank lines and lines that start
with # are not records. Nested JSON is not read. A JSON array is rejected.

Logical fields
  timestamp   required    ISO-8601. A trailing Z is UTC. No offset is read as UTC.
  agent       optional    Agent or bot name.
  trigger     optional    What started the run, such as schedule, event, or manual.
  routine     optional    Routine or task name.
  units       optional    Tokens or other cost units. A number. Blank stays blank.
  outcome     optional    What the run did. See the default classes below.
  duration    optional    Numeric values print as numbers. Other values print as written. Not summed.
  error       optional    Error text. Repeats group on agent, routine, and this text.

Default keys are the logical names. A config file maps them onto your columns.
Omitted mapping keys keep the defaults. Copy usage-audit.example.yaml to
usage-audit.yaml, or pass --config.

mapping:
  timestamp: ts
  agent: bot
  trigger: trigger
  routine: routine
  units: tokens
  outcome: outcome
  duration: duration_ms
  error: error
top: 10
retry_min: 2
outcomes:
  noop: ["no-op", "noop", "unchanged"]
  changed: ["changed"]
  error: ["error", "failed", "failure"]
triggers:
  schedule: ["schedule", "cron", "timer"]

Outcome and trigger labels are matched case-insensitively.
Unknown outcomes stay in "other". They are not counted as a change or a no-op.
Schedule rows are those whose trigger is in triggers.schedule.

Unit totals are sums of the units field on rows that recorded a finite number.
Rows that omit units are counted in run totals and are not given a filled-in
value. Rows whose units field is present but not a number are counted separately
and are not treated as zero.
"""
