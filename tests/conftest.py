# -*- coding: utf-8 -*-
"""pytest configuration: add the repository root to the import path so that ``import ctp_core`` resolves."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
