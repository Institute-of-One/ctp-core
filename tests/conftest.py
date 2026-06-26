# -*- coding: utf-8 -*-
"""pytest 設定: リポジトリ root を import パスへ追加し ``import ctp_core`` を解決する。"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
