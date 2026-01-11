def test_pytest_is_running():
    """Basic sanity test."""
    assert True


def test_qgis_available(qgis_app):
    """Test QGIS application fixture provided by pytest-qgis."""
    assert qgis_app is not None
