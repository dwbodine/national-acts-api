from importlib.machinery import SourceFileLoader
import os
import sys


wsgi = SourceFileLoader('wsgi', os.path.join(os.path.dirname(__file__), 'app.py')).load_module()
application = wsgi.application
