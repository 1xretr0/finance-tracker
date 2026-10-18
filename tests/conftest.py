import os

# Keep a developer's real .env out of the suite (must be set before backend.constants is first imported).
os.environ["ENV_FILE"] = os.devnull
