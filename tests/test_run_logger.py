"""Tests for run quality logger."""

import pytest

from src.core.run_logger import log_run, read_run_log, list_csv_files, RUN_LOG_PATH


@pytest.fixture(autouse=True)
def use_tmp_outputs(tmp_path, monkeypatch):
    """Redirect outputs/ to a temp directory for all tests."""
    monkeypatch.setattr("src.core.run_logger.OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("src.core.run_logger.RUN_LOG_PATH", tmp_path / "run_log.csv")


class TestRunLogger:
    def test_log_creates_file(self, tmp_path):
        log_run("test.csv", "good", "nice run")
        assert (tmp_path / "run_log.csv").exists()

    def test_log_appends_rows(self, tmp_path):
        log_run("test1.csv", "good")
        log_run("test2.csv", "bad", "noisy data")
        df = read_run_log()
        assert len(df) == 2
        assert df.iloc[0]["rating"] == "good"
        assert df.iloc[1]["rating"] == "bad"
        assert df.iloc[1]["notes"] == "noisy data"

    def test_read_empty_log(self):
        df = read_run_log()
        assert len(df) == 0
        assert "rating" in df.columns

    def test_list_csv_files(self, tmp_path):
        # Create some dummy CSV files
        (tmp_path / "rhs_2026-03-03_10-00-00.csv").write_text("header\n")
        (tmp_path / "rhs_2026-03-03_11-00-00.csv").write_text("header\n")
        (tmp_path / "other.csv").write_text("header\n")  # Should not match

        files = list_csv_files()
        assert len(files) == 2
        assert all(f.startswith("rhs_") for f in files)
