# -*- coding: utf-8 -*-
"""Add the path that lets ctp_core resolve even when a test file is run directly."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
