# ---------------------------------------------------------------------------
# Static guards for the container packaging. The image is only built in CI, so
# these pin the settings that are easy to regress and hard to notice locally.
# ---------------------------------------------------------------------------
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _compose_environment():
    text = (ROOT / "docker-compose.yml").read_text()
    block = re.search(r"^\s+environment:\n((?:\s+- .+\n)+)", text, re.M)
    assert block, "docker-compose.yml has no environment: list"
    return set(re.findall(r"- (\S+)", block.group(1)))


def test_compose_forces_container_settings_over_env_file():
    # env_file values override the image ENV, so a local-run .env (blank PORT,
    # OAUTH_BIND_ADDR=localhost) would break the container unless compose pins these
    assert {"DATA_DIR=/data", "OAUTH_BIND_ADDR=0.0.0.0", "PORT=5000"} <= _compose_environment()


def test_compose_publishes_the_dashboard_on_loopback_only():
    text = (ROOT / "docker-compose.yml").read_text()
    assert '"127.0.0.1:5000:5000"' in text


def test_dockerfile_runs_one_worker_with_exec_and_long_timeout():
    cmd = re.search(r"^CMD (.+)$", (ROOT / "Dockerfile").read_text(), re.M).group(1)
    assert cmd.startswith("exec gunicorn backend.server:app")
    assert "--workers 1" in cmd
    assert "--timeout 300" in cmd
