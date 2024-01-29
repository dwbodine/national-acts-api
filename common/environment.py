import os
import sys

def loadEnv():
    path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(path):
        f = open(path, 'r')
        for x in f:
            env = x.split('=')
            key = env[0].strip()
            val = env[1].strip()
            if (key in os.environ) == False:
                os.environ[key] = val       
        f.close()



