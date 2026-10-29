# Contributing

Thanks for looking at usage-audit. Keep changes small, and cover them with tests.

## Setup

Python 3.10 or newer. The runtime dependency is PyYAML. Tests use pytest and do not need a network.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Guidelines

- Do not add secrets, tokens, or personal data to the repo, tests, fixtures, or logs.
- The sample log under `examples/` is synthetic. Keep the label that says so.
- Every number in the report is a count or a sum of fields present in the input window. Do not fill in missing units, and do not convert units into money.
- `usage-audit report` may print a qualitative suggestion (slow a schedule, or gate it with wakegate). It must not invent a cron expression or a cost that is not in the log.
