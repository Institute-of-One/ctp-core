"""Console setup shared by the drivers.

Each driver used to start with ``sys.stdout = io.TextIOWrapper(sys.stdout.buffer, ...)``. That
is right on a Windows console whose code page cannot encode the output, and wrong everywhere
else: it raises AttributeError when stdout has no ``buffer`` -- under a test that captures
output, or inside a pipeline that replaces the stream -- and it leaves the replacement behind
for whatever runs next. A driver that cannot be called from a test cannot be tested, and a
reviewer pointed out that none of the drivers' entry points were.
"""

from __future__ import annotations

import contextlib
import io
import sys


def use_utf8_stdout() -> None:
    """Make stdout carry UTF-8 if it can, and leave it alone if it cannot.

    Three cases, in order of preference: a stream that can be reconfigured is reconfigured; a
    stream with an underlying binary buffer is wrapped, as before; anything else -- a StringIO
    under a test, for instance -- is left exactly as it is.
    """
    with contextlib.suppress(AttributeError, OSError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        with contextlib.suppress(OSError, ValueError):
            sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace",
                                          line_buffering=True)
