import os
import shutil
import tempfile
import pytest

# Create a temporary directory for the test run
test_data_dir = tempfile.mkdtemp(prefix="kattappa_test_")
os.environ["KATTAPPA_DATA_DIR"] = test_data_dir

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data():
    yield
    # Cleanup temp directory after test session finishes
    shutil.rmtree(test_data_dir, ignore_errors=True)
