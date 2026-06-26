# -*- coding: utf-8 -*-
"""pytest 不在環境向けの簡易テストランナー。

使い方 (各テストファイル末尾):
    if __name__ == "__main__":
        import _runner; _runner.run(globals())
"""

import sys


def run(namespace) -> int:
    funcs = [
        (name, obj) for name, obj in sorted(namespace.items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = failed = 0
    for name, fn in funcs:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed (of {len(funcs)})")
    code = 0 if failed == 0 else 1
    sys.exit(code)
