#!/usr/bin/env python3
"""Run every test:  python3 tests/run_all.py   (PowerShell tests run if pwsh is on PATH or $PWSH is set)."""
import os
import sys
import unittest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(here))
suite = unittest.defaultTestLoader.discover(here, pattern="test_*.py", top_level_dir=os.path.dirname(here))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
