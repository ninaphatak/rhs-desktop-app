"""RHS Monitor — main application entry point."""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="RHS Monitor")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock Arduino and camera data (no hardware needed)",
    )
    return parser.parse_args()


def main() -> None:
    """Launch the RHS Monitor application."""
    args = parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("RHS Monitor")

    window = MainWindow(mock=args.mock)
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
