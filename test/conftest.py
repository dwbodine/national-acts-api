"""
Shared pytest fixtures for the national-acts-api test suite.
"""

import shutil
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def workspace_tmp_path():
    """
    Provide a writable temp directory inside the workspace for Windows sandbox runs.
    """
    root = Path.cwd() / "test_runtime"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
