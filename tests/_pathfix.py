# -*- coding: utf-8 -*-
"""スタンドアロン実行 (python tests/test_x.py) でも ctp_core を解決するための共通パス追加。"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
