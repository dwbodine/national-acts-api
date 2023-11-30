import os
import sys

def loadEnv():
    f = open(os.path.join(os.path.dirname(__file__), '.env'), 'r')
    for x in f:
        env = x.split('=')
        key = env[0].strip()
        val = env[1].strip()
        os.environ[key] = val       
    f.close()



