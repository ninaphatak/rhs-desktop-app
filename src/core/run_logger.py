"""Append-only run quality logger (outputs/run_log.csv)."""

import csv
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.utils.config import RUN_LOG_PATH, OUTPUTS_DIR

logger = logging.getLogger(__name__)

RUN_LOG_HEADERS = ["timestamp", "csv_filename", "rating", "notes"]


def log_run(csv_filename: str, rating: str, notes: str = "") -> None:
    """Append a run rating entry to run_log.csv.

    Args:
        csv_filename: Name of the CSV file being rated.
        rating: One of 'good', 'bad', 'neutral'.
        notes: Optional freeform notes.
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not RUN_LOG_PATH.exists()

    with open(RUN_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(RUN_LOG_HEADERS)
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            csv_filename,
            rating,
            notes,
        ])

    logger.info(f"Logged run: {csv_filename} = {rating}")


def read_run_log() -> pd.DataFrame:
    """Read the run log into a DataFrame. Returns empty DF if file missing."""
    if not RUN_LOG_PATH.exists():
        return pd.DataFrame(columns=RUN_LOG_HEADERS)
    return pd.read_csv(RUN_LOG_PATH)


def list_csv_files() -> list[str]:
    """List CSV files in the outputs/ directory (newest first)."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(OUTPUTS_DIR.glob("rhs_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [f.name for f in files]
