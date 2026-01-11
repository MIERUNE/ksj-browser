import os
import sys
from pathlib import Path


def pytest_configure():
    """Configure pytest environment for tests.

    Add project root to sys.path for imports.

    Note: QGIS environment variables (DYLD_LIBRARY_PATH, PROJ_LIB, GDAL_DATA)
    must be set BEFORE running pytest, as pytest-qgis imports QGIS at plugin
    load time. Use: source setup_qgis_env.sh
    """

    # Add project root to sys.path
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, os.fspath(project_root))
