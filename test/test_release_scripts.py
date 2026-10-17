"""Exercise release orchestration with Docker and AWS replaced by local stubs."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

NEW_IMAGE = (
    "804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi@sha256:"
    + "a" * 64
)
OLD_IMAGE = (
    "804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi@sha256:"
    + "b" * 64
)
HARNESS = r"""
docker() {
  printf 'docker %s\n' "$*" >> "$TEST_LOG"
  case "$*" in
    inspect*) printf 'sha256:old-local-id\n' ;;
    'image inspect'*) printf '%s\n' "$OLD_IMAGE" ;;
    *'tools.migrate current') printf '0001_baseline\n' ;;
    *'tools.migrate upgrade') [[ "$SCENARIO" != migration-failure ]] ;;
    *'exec -T nationalactsdb'*) printf '%s\n' 'CREATE TABLE backup_test (id INT);' ;;
    *'exec -T nationalactsapi'*) [[ "$SCENARIO" != readiness-failure ]] ;;
    *'up -d --no-deps nationalactsapi') printf 'activated %s\n' "$API_IMAGE" >> "$TEST_LOG" ;;
  esac
}
aws() {
  printf 'aws %s\n' "$*" >> "$TEST_LOG"
  [[ "$SCENARIO" != backup-failure ]] || return 1
  local from="$3" to="$4"
  if [[ "$from" == s3://* ]]; then from="$TEST_REMOTE/${from##*/}"; fi
  if [[ "$to" == s3://* ]]; then to="$TEST_REMOTE/${to##*/}"; fi
  cp "$from" "$to"
}
flock() { return 0; }
sleep() { return 0; }
export -f docker aws flock sleep
bash "$SCRIPT_TO_RUN" "$NEW_IMAGE"
"""


@pytest.fixture
def release_runner(tmp_path):
    """Return a function that runs the release script with a given scenario."""
    bash = shutil.which("bash")
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if os.name == "nt":
        bash = str(git_bash) if git_bash.exists() else None
    if not bash:
        pytest.skip("Bash is required for deployment script checks")
    source = Path(__file__).resolve().parents[1] / "aws"
    for name in ("release-common.sh", "release-api.sh", "rollback-api.sh"):
        shutil.copy(source / name, tmp_path / name)
    remote = tmp_path / "s3"
    remote.mkdir()
    log = tmp_path / "events.log"

    def run(script="release-api.sh", scenario="healthy"):
        env = dict(
            os.environ,
            TEST_LOG=log.as_posix(),
            TEST_REMOTE=remote.as_posix(),
            SCRIPT_TO_RUN=(tmp_path / script).as_posix(),
            SCENARIO=scenario,
            NEW_IMAGE=NEW_IMAGE,
            OLD_IMAGE=OLD_IMAGE,
            BACKUP_S3_PREFIX="s3://test-bucket/pre-deploy",
        )
        env.pop("API_IMAGE", None)
        env.pop("RELEASE_STATE_DIR", None)
        result = subprocess.run(
            [bash, "-c", HARNESS], env=env, capture_output=True, text=True, timeout=30
        )
        return result, log.read_text(), tmp_path

    return run


def test_release_and_rollback_exact_images(release_runner):
    """Test that a release and rollback can be performed with exact images."""
    result, events, directory = release_runner()
    assert result.returncode == 0, result.stderr
    assert events.index("aws s3 cp") < events.index("tools.migrate upgrade")
    assert events.index("tools.migrate check") < events.index("activated " + NEW_IMAGE)
    assert (directory / ".releases/current-image").read_text().strip() == NEW_IMAGE
    result, events, directory = release_runner("rollback-api.sh")
    assert result.returncode == 0, result.stderr
    activations = [
        line for line in events.splitlines() if line.startswith("activated ")
    ]
    assert activations[-1] == "activated " + OLD_IMAGE
    assert (directory / ".releases/current-image").read_text().strip() == OLD_IMAGE
    assert "tools.migrate downgrade" not in events
    assert "down -v" not in events


@pytest.mark.parametrize(
    "scenario", ["backup-failure", "migration-failure", "readiness-failure"]
)
def test_release_failure_stops_at_correct_stage(release_runner, scenario):
    result, events, directory = release_runner(scenario=scenario)
    assert result.returncode != 0
    assert not (directory / ".releases/current-image").exists()
    if scenario == "backup-failure":
        assert "tools.migrate upgrade" not in events
    if scenario in ("backup-failure", "migration-failure"):
        assert "activated " not in events
    else:
        assert "activated " + NEW_IMAGE in events
        result, events, directory = release_runner("rollback-api.sh")
        assert result.returncode == 0, result.stderr
        assert (directory / ".releases/current-image").read_text().strip() == OLD_IMAGE
