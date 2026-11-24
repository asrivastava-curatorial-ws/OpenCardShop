"""Test settings: per-user files go to a temporary folder, and only bundled fonts are used."""
import atexit
import os
import shutil
import tempfile

if "OPENCARDSHOP_HOME" not in os.environ:
    _home = tempfile.mkdtemp(prefix="opencardshop-tests-")
    os.environ["OPENCARDSHOP_HOME"] = _home
    atexit.register(shutil.rmtree, _home, ignore_errors=True)
os.environ.setdefault("OPENCARDSHOP_NO_SYSTEM_FONTS", "1")
