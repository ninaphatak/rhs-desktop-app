"""Tests for ReviewDialog session discovery."""

import pytest
from pathlib import Path

from src.ui.review_dialog import discover_sessions


class TestSessionDiscovery:
    """Test discover_sessions finds matching CSV + video triples."""

    def test_discovers_complete_session(self, tmp_path: Path) -> None:
        """A session with CSV + 2 videos should be discovered."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        (tmp_path / "rhs_2026-04-08_14-30-00.csv").touch()
        (videos_dir / "camera1_2026-04-08_14-30-00.avi").touch()
        (videos_dir / "camera2_2026-04-08_14-30-00.avi").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 1
        assert sessions[0]["timestamp"] == "2026-04-08_14-30-00"

    def test_ignores_csv_without_videos(self, tmp_path: Path) -> None:
        """A CSV without matching videos should not appear."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        (tmp_path / "rhs_2026-04-08_14-30-00.csv").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 0

    def test_ignores_partial_videos(self, tmp_path: Path) -> None:
        """A CSV with only one matching video should not appear."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        (tmp_path / "rhs_2026-04-08_14-30-00.csv").touch()
        (videos_dir / "camera1_2026-04-08_14-30-00.avi").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 0

    def test_multiple_sessions_sorted_newest_first(self, tmp_path: Path) -> None:
        """Multiple sessions should be returned newest first."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        for ts in ["2026-04-08_14-30-00", "2026-04-08_15-00-00"]:
            (tmp_path / f"rhs_{ts}.csv").touch()
            (videos_dir / f"camera1_{ts}.avi").touch()
            (videos_dir / f"camera2_{ts}.avi").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 2
        assert sessions[0]["timestamp"] == "2026-04-08_15-00-00"

    def test_session_contains_all_paths(self, tmp_path: Path) -> None:
        """Each session dict should contain csv, cam1, cam2 paths."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        ts = "2026-04-08_14-30-00"
        (tmp_path / f"rhs_{ts}.csv").touch()
        (videos_dir / f"camera1_{ts}.avi").touch()
        (videos_dir / f"camera2_{ts}.avi").touch()

        session = discover_sessions(tmp_path)[0]
        assert session["csv"] == tmp_path / f"rhs_{ts}.csv"
        assert session["cam1"] == videos_dir / f"camera1_{ts}.avi"
        assert session["cam2"] == videos_dir / f"camera2_{ts}.avi"
