#!/bin/bash
# QGIS environment setup for pytest-qgis (macOS)
# Source this file before running tests: source setup_qgis_env.sh

export DYLD_LIBRARY_PATH=/Applications/QGIS.app/Contents/MacOS/lib:$DYLD_LIBRARY_PATH
export PROJ_LIB=/Applications/QGIS.app/Contents/Resources/proj
export GDAL_DATA=/Applications/QGIS.app/Contents/Resources/gdal

echo "QGIS environment variables set for pytest-qgis"
