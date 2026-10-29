"""Repo path for fixtures."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLE_JSONL = REPO / "examples" / "sample-runs.jsonl"
SAMPLE_CSV = REPO / "examples" / "sample-runs.csv"
EXAMPLE_CONFIG = REPO / "usage-audit.example.yaml"
