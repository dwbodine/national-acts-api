"""
WSGI implementation module
"""

from importlib.machinery import SourceFileLoader
import os


wsgi = SourceFileLoader(
    "wsgi", os.path.join(os.path.dirname(__file__), "app.py")
).load_module()
application = wsgi.application
