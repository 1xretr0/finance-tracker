# ---------------------------------------------------------------------------
# The suite must not depend on the developer's shell: values exported for
# running the app (direnv, `set -a; . .env`) would otherwise be baked into
# backend.constants at import and change what the tests see.
# ---------------------------------------------------------------------------
import os

import backend.constants as constants
from tests.conftest import CONFIG_ENV_VARS


def test_exported_config_variables_are_hidden_from_the_suite():
    assert [name for name in CONFIG_ENV_VARS if name in os.environ] == []


def test_constants_do_not_pick_up_exported_config():
    assert constants.ADMIN_USERNAME is None
    assert constants.DATA_DIR is None
