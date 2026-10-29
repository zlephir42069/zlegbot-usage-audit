# usage-audit

usage-audit reads a log of AI-agent runs and totals the units that log already recorded. It shows which agent, routine, trigger, and day account for the spend, which routines wake without changing anything, which schedules fire more often than they record a change, and which errors repeat.

The tool does not call a model and does not open a network connection. It does not invent a unit value for a row that left the field blank, and it does not convert units into money.

Part of the tools at <https://github.com/zlephir42069>.

## Why it saves credits

A scheduled agent spends credits on every wake, including wakes that change nothing and retries of an error it already logged. The log is the place those costs were written down. usage-audit adds up the recorded units on those rows so you can delete a routine, slow a schedule, or stop retrying the same error. The totals are only the rows in the file. They are not a forecast of what an unwoken run would have cost.

When a schedule fires more often than it records a change, the report says so and points at a cron-first gate. [zlegbot-wakegate](https://github.com/zlephir42069/zlegbot-wakegate) runs the cheap checks on the timer and starts the agent only after a check fires. usage-audit does not start that gate and does not propose a cron expression.

## 60-second quickstart

Requires Python 3.10+.

```bash
python -m pip install -e .
usage-audit schema
usage-audit validate examples/sample-runs.jsonl
usage-audit report examples/sample-runs.jsonl
usage-audit report examples/sample-runs.csv --json
```

`python -m usage_audit` is the same entry point. `examples/sample-runs.jsonl` and `examples/sample-runs.csv` are synthetic example data, not a measured log. The first line of each file says so.

Copy `usage-audit.example.yaml` to `usage-audit.yaml` when your columns use different names. `usage-audit report` and `usage-audit validate` load `usage-audit.yaml` from the current directory when it exists.

## Config reference

`usage-audit.yaml` is optional. Relative paths are resolved from the current directory. `--config` uses that file instead, and the path must exist. The file is not read by `usage-audit schema`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `mapping` | logical field names | JSON key or CSV column for each field. Omitted keys keep the default name. |
| `top` | `10` | How many costliest runs to list. `--top` overrides it. |
| `retry_min` | `2` | Minimum occurrences before an identical error is listed. |
| `outcomes` | see below | Case-insensitive labels for no-op, changed, and error. |
| `triggers.schedule` | `schedule`, `cron`, `timer` | Trigger labels treated as a schedule. |

Default outcome labels:

| Class | Labels |
| --- | --- |
| no-op | `no-op`, `noop`, `unchanged` |
| changed | `changed` |
| error | `error`, `failed`, `failure` |

Any other outcome, including a blank one, stays `other`. It is not counted as a change or a no-op.

A mapping example, also printed by `usage-audit schema`:

```yaml
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
```

Quote values that YAML would otherwise read as numbers or timestamps. Unknown keys are a config error.

Logical fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `timestamp` | yes | ISO-8601. A trailing `Z` is UTC. A value with no offset is read as UTC. |
| `agent` | no | Agent or bot name. |
| `trigger` | no | What started the run, such as `schedule`, `event`, or `manual`. |
| `routine` | no | Routine or task name. |
| `units` | no | Tokens or other cost units. A finite number. Blank stays blank. |
| `outcome` | no | What the run did. Classified with the labels above. |
| `duration` | no | Numeric values print as numbers. Other values print as written. Not summed and not converted. |
| `error` | no | Error text. Repeats group on agent, routine, and this text. |

JSONL is one JSON object per line (`.jsonl`, `.ndjson`, `.json`). CSV has a header row. The suffix selects the parser. A suffix that is neither of those is sniffed: a first record that starts with `{` is JSONL, otherwise CSV. Nested JSON is not read. A JSON array is rejected. Blank lines and lines that start with `#` are not records.

## Commands

Exit codes for every command: `0` ok, `1` the log is missing, unreadable, or `validate` rejected rows, `2` a usage or config error.

### `usage-audit schema`

Prints the fields and a mapping example. It does not read a log.

### `usage-audit validate <logs>`

Checks that each file parses and that every record has a timestamp. A units field that is present but not a finite number is an error. A missing units field is allowed. The command exits `1` and prints one `log error:` line per problem (up to 50, then a count of the rest). It does not apply `--since` or `--until`.

### `usage-audit report <logs>`

Prints a Markdown report. `--json` prints the same totals as JSON. Unit amounts in JSON are decimal strings, summed with decimal arithmetic.

```bash
usage-audit report runs.jsonl runs.csv
usage-audit report runs.jsonl --since 7d --until 2026-10-31T00:00:00Z --top 5
usage-audit report runs.jsonl --json
```

`--since` is a duration (`30s`, `15m`, `12h`, `7d`, `1w`) or an inclusive ISO timestamp. A duration is subtracted from the latest parsed timestamp in the file, not from the clock. `--until` is an inclusive ISO timestamp. Rows outside that range are counted as `rows outside window` and are not part of the totals. The report prints both the file span and the input window.

Malformed rows are listed and omitted from every total. `report` still exits `0` when some rows are malformed. `validate` is the command that fails on them.

## What the report computes

Every figure is a count of rows or a sum of the `units` field on rows inside the input window.

- **Spend by agent, routine, trigger, and day.** Runs and the sum of recorded units. Days are the UTC date. Names are grouped case-insensitively, and the report shows the first spelling in the file.
- **No-op wakes by routine.** `no-op runs / runs`, and the sum of units on the no-op rows. A no-op row with no units adds to the count only.
- **Schedules.** For each routine whose trigger is a schedule label: fires, changes, no-ops, errors, other, and the sum of units on those schedule rows. The row is flagged when fires are greater than changes. Gaps are the seconds between consecutive rows. The median of an even number of gaps is the mean of the two central gaps. When any row is flagged, the report suggests a slower cadence or a cron-first wake gate such as zlegbot-wakegate. It does not print a replacement cron expression.
- **Repeated identical errors.** The same agent, routine, and error text, compared case-insensitively. A retry loop is a consecutive run of that text. A different outcome or a different error text breaks the run. Occurrences count every matching row, and units are the sum recorded on them. A group is listed when occurrences are at least `retry_min`.
- **Top runs.** The rows with the largest recorded units. Rows that omit units, or whose units do not parse, are left out of this ranking. They are not treated as zero. A recorded zero stays in the ranking.

An empty window prints zero runs and a units total of zero. That is the sum of no rows, and the input window line says `empty`.

## Example

`examples/sample-runs.jsonl` is synthetic example data: ten made-up runs for `inbox-bot` / `poll-inbox` and `digest-bot` / `daily-digest`. It is not measured usage.

Summing the `units` field on those ten rows gives 1850 units. The input window printed for that file is `2026-10-01T00:00:00Z .. 2026-10-02T12:00:00Z`. From the same rows: `poll-inbox` has 3 no-op runs out of 6, recording 300 units on the no-op rows; `daily-digest` has 1 no-op run out of 4, recording 10 units. Each routine's schedule fires 4 times and records 1 change. The two `upstream timeout` rows on `digest-bot` / `daily-digest` are a retry loop and record 800 units. `usage-audit report examples/sample-runs.jsonl` prints those sums. The CSV twin is the same ten rows.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

See `CONTRIBUTING.md`. Tests are offline. The license is MIT, copyright zlephir42069.
