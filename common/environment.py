"""
Environment variable service
"""
import os

def load_env():
    """
    Load environment vars for local dev
    """
    path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(path):
        f = open(path, 'r', encoding="utf-8")
        for x in f:
            env = x.split('=')
            key = env[0].strip()
            val = env[1].strip()
            if (key in os.environ) is False:
                os.environ[key] = val
        f.close()



