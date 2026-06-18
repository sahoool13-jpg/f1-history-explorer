"""Shared paths and helpers for the F1 History Explorer Phase A pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PARQUET = ROOT / "data" / "parquet"
BUILD = ROOT / "build"
DB_PATH = BUILD / "f1.duckdb"

# Ergast CSV exports use the literal string "\N" to denote NULL.
NULLSTR = "\\N"

# Every raw CSV we expect to find, in load order.
RAW_TABLES = [
    "circuits",
    "constructors",
    "drivers",
    "seasons",
    "status",
    "races",
    "results",
    "sprint_results",
    "qualifying",
    "driver_standings",
    "constructor_standings",
    "constructor_results",
    "pit_stops",
    "lap_times",
]


def connect():
    import duckdb

    BUILD.mkdir(parents=True, exist_ok=True)
    PARQUET.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))
