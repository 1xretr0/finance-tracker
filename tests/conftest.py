import os

# Every variable backend/constants.py reads (ENV_FILE is pinned below).
CONFIG_ENV_VARS = (
    "ADMIN_PASSWORD", "ADMIN_USERNAME", "API_TOKEN", "CREDENTIALS_PATH", "DATA_DIR",
    "DB_PATH", "DEPLOY_RELOAD_FILE", "DEPLOY_REPO_DIR", "FLASK_DEBUG",
    "GITHUB_WEBHOOK_SECRET", "OAUTH_BIND_ADDR", "PORT", "REMOTE_API_URL",
    "TOKEN_PATH", "TRUST_PROXY",
)

# Keep a developer's real .env and exported shell config out of the suite
# (must happen before backend.constants is first imported).
os.environ["ENV_FILE"] = os.devnull
for _name in CONFIG_ENV_VARS:
    os.environ.pop(_name, None)
