# Example logs

`sample-runs.jsonl` and `sample-runs.csv` are the same ten synthetic runs.
They are example data for the command help and the tests. They are not a
real agent log, and the unit totals are not measured spend.

The first line of each file says so. `usage-audit` skips blank lines and
lines that start with `#`.

Recompute any total by summing the `units` field on the rows you care about.
The report prints that sum. It does not add a cost for a row that has no units.
