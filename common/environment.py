"""
Environment variable service
"""

import os

from common.utility import get_override_string_value_or_default


def load_env():
    """
    Load environment vars for local dev
    """
    path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(path):
        f = open(path, "r", encoding="utf-8")
        for x in f:
            env = x.split("=")
            if len(env) > 1:
                key = get_override_string_value_or_default(env[0])
                val = get_override_string_value_or_default(env[1])
                if (key in os.environ) is False:
                    os.environ[key] = val
        f.close()
