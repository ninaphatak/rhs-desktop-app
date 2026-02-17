"""
Shared pytest fixtures and configuration.

Sets up Qt platform for headless testing on macOS.
"""

import os
import sys
from pathlib import Path

# Set Qt plugin path before any Qt imports
_pyqt6_plugins = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "PyQt6" / "Qt6" / "plugins"
if _pyqt6_plugins.exists():
    os.environ.setdefault("QT_PLUGIN_PATH", str(_pyqt6_plugins))

# Use offscreen platform for CI/headless testing
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
